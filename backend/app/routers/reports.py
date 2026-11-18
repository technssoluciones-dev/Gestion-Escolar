"""Planillas y reportes descargables (Excel) y certificado de alumno regular."""
import json
import re
import unicodedata
from calendar import monthrange
from collections import defaultdict
from datetime import date as DateType
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..database import get_db
from ..models import (
    Attendance,
    CertificateSignature,
    Course,
    CourseSubject,
    Fee,
    Grade,
    Student,
    Subject,
)
from ..security import require_management, require_staff
from ..signing import canonical, code_for, sign

router = APIRouter(prefix="/reports", tags=["Reportes"], dependencies=[Depends(require_staff)])

APPROVAL = 4.0
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

TITLE_FONT = Font(bold=True, size=15, color="1F2937")
SUBTITLE_FONT = Font(size=10, color="5B6B7C")
HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
TOTAL_FILL = PatternFill("solid", fgColor="DDE7F0")
THIN = Side(style="thin", color="C9D2DC")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")

STATUS_LETTER = {"presente": "P", "ausente": "A", "atrasado": "T", "justificado": "J"}
STATUS_FILLS = {
    "presente": PatternFill("solid", fgColor="D9EAD3"),
    "ausente": PatternFill("solid", fgColor="F4CCCC"),
    "atrasado": PatternFill("solid", fgColor="FCE5CD"),
    "justificado": PatternFill("solid", fgColor="DCE8F7"),
}


def _course_or_404(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curso no encontrado")
    return course


def _students(db: Session, course_id: int) -> list[Student]:
    return list(
        db.scalars(
            select(Student)
            .where(Student.course_id == course_id, Student.is_active.is_(True))
            .order_by(Student.last_name, Student.first_name)
        ).all()
    )


def _assignments(db: Session, course_id: int) -> list[CourseSubject]:
    return list(
        db.scalars(
            select(CourseSubject)
            .options(
                joinedload(CourseSubject.subject), joinedload(CourseSubject.teacher)
            )
            .join(Subject, Subject.id == CourseSubject.subject_id)
            .where(CourseSubject.course_id == course_id)
            .order_by(Subject.name)
        ).all()
    )


def _weighted_average(grades: list[Grade]) -> float | None:
    total_weight = sum(g.weight for g in grades)
    if not total_weight:
        return None
    return round(sum(float(g.score) * g.weight for g in grades) / total_weight, 1)


def _mean(values: list[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    return round(sum(valid) / len(valid), 1) if valid else None


def _slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-") or "curso"


def _xlsx(wb: Workbook, filename: str) -> StreamingResponse:
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type=XLSX_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _sheet(wb: Workbook, title: str) -> "Worksheet":
    ws = wb.active if wb.active.max_row == 1 and wb.active["A1"].value is None else wb.create_sheet()
    ws.title = title[:31]
    ws.sheet_view.showGridLines = False
    return ws


def _title_block(ws, title: str, lines: list[str], ncols: int) -> int:
    last = get_column_letter(max(ncols, 1))
    ws.merge_cells(f"A1:{last}1")
    ws["A1"] = title
    ws["A1"].font = TITLE_FONT
    ws["A1"].alignment = LEFT
    ws.row_dimensions[1].height = 24
    row = 2
    for line in lines:
        ws.merge_cells(f"A{row}:{last}{row}")
        ws[f"A{row}"] = line
        ws[f"A{row}"].font = SUBTITLE_FONT
        ws[f"A{row}"].alignment = LEFT
        row += 1
    return row + 1


def _header(ws, row: int, headers: list[str]) -> None:
    for col, text in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col, value=text)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        cell.border = BORDER
    ws.row_dimensions[row].height = 20


def _body(ws, row: int, col: int, value, *, center: bool = True, fill=None, bold: bool = False):
    cell = ws.cell(row=row, column=col, value=value)
    cell.border = BORDER
    cell.alignment = CENTER if center else LEFT
    cell.font = Font(bold=bold, color="B91C1C" if isinstance(value, (int, float)) and value < APPROVAL else "1F2937")
    if fill:
        cell.fill = fill
    return cell


def _widths(ws, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width


@router.get("/courses/{course_id}/grades.xlsx")
def grades_sheet(
    course_id: int,
    subject_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Planilla de notas del curso: una hoja por asignatura, con evaluaciones y promedios."""
    course = _course_or_404(db, course_id)
    assignments = _assignments(db, course.id)
    if subject_id is not None:
        assignments = [a for a in assignments if a.subject_id == subject_id]
        if not assignments:
            raise HTTPException(422, "El curso no tiene asignada esa asignatura")
    if not assignments:
        raise HTTPException(422, "El curso no tiene asignaturas asignadas")

    students = _students(db, course.id)
    grades = list(
        db.scalars(
            select(Grade)
            .where(Grade.course_id == course.id)
            .order_by(Grade.date, Grade.id)
        ).all()
    )
    by_student_subject: dict[tuple[int, int], list[Grade]] = defaultdict(list)
    for grade in grades:
        by_student_subject[(grade.student_id, grade.subject_id)].append(grade)

    wb = Workbook()
    evaluation_rows = list(
        db.scalars(
            select(CourseSubject)
            .options(joinedload(CourseSubject.evaluations))
            .where(CourseSubject.course_id == course.id)
        ).unique().all()
    )
    evaluations_by_subject = {
        assignment.subject_id: sorted(assignment.evaluations, key=lambda e: (e.date, e.id))
        for assignment in evaluation_rows
    }

    if len(assignments) > 1:
        summary = _sheet(wb, "Resumen")
        cols = ["RUT", "Estudiante"] + [a.subject.name for a in assignments] + ["Promedio general"]
        row = _title_block(
            summary,
            f"Promedios por asignatura · {course.name}",
            [f"Año {course.year}" + (f" · Profesor jefe: {course.head_teacher_name}" if course.head_teacher_name else "")],
            len(cols),
        )
        _header(summary, row, cols)
        first_data = row + 1
        for offset, student in enumerate(students):
            current = first_data + offset
            _body(summary, current, 1, student.rut, center=False)
            _body(summary, current, 2, student.full_name, center=False)
            averages = []
            for index, assignment in enumerate(assignments, start=3):
                average = _weighted_average(
                    by_student_subject.get((student.id, assignment.subject_id), [])
                )
                averages.append(average)
                _body(summary, current, index, average)
            _body(summary, current, len(assignments) + 3, _mean(averages), bold=True, fill=TOTAL_FILL)
        if students:
            total_row = first_data + len(students)
            _body(summary, total_row, 1, "", fill=TOTAL_FILL)
            _body(summary, total_row, 2, "Promedio del curso", center=False, bold=True, fill=TOTAL_FILL)
            for index, assignment in enumerate(assignments, start=3):
                column_average = _mean(
                    [
                        _weighted_average(by_student_subject.get((s.id, assignment.subject_id), []))
                        for s in students
                    ]
                )
                _body(summary, total_row, index, column_average, bold=True, fill=TOTAL_FILL)
            _body(summary, total_row, len(assignments) + 3, "", fill=TOTAL_FILL)
        _widths(summary, [14, 34] + [16] * len(assignments) + [14])
        summary.freeze_panes = f"C{first_data}"

    used_names: set[str] = {"Resumen"}
    for assignment in assignments:
        base_name = re.sub(r"[\[\]:*?/\\]", " ", assignment.subject.name).strip() or "Asignatura"
        name = base_name[:31]
        suffix = 2
        while name in used_names:
            name = f"{base_name[:28]} {suffix}"
            suffix += 1
        used_names.add(name)

        ws = _sheet(wb, name)
        evaluations = evaluations_by_subject.get(assignment.subject_id, [])
        free_titles: dict[str, tuple] = {}
        for grade in grades:
            if grade.subject_id != assignment.subject_id or grade.evaluation_id is not None:
                continue
            free_titles.setdefault(grade.title, (grade.title, grade.date, grade.weight, None))
        columns = [(e.title, e.date, e.weight, e.id) for e in evaluations] + list(free_titles.values())

        teacher_line = f"Profesor: {assignment.teacher.full_name}" if assignment.teacher else "Profesor sin asignar"
        cols = ["RUT", "Estudiante"] + [title for title, *_ in columns] + ["Promedio ponderado"]
        row = _title_block(
            ws,
            f"Planilla de notas · {assignment.subject.name}",
            [f"{course.name} · Año {course.year} · {teacher_line}"],
            len(cols),
        )
        _header(ws, row, cols)
        first_data = row + 1
        for offset, student in enumerate(students):
            current = first_data + offset
            _body(ws, current, 1, student.rut, center=False)
            _body(ws, current, 2, student.full_name, center=False)
            student_grades = by_student_subject.get((student.id, assignment.subject_id), [])
            by_evaluation = {g.evaluation_id: g for g in student_grades if g.evaluation_id}
            by_title = {}
            for grade in student_grades:
                if grade.evaluation_id is None:
                    by_title.setdefault(grade.title, grade)
            for index, (title, _, _, evaluation_id) in enumerate(columns, start=3):
                grade = by_evaluation.get(evaluation_id) if evaluation_id else by_title.get(title)
                _body(ws, current, index, float(grade.score) if grade else None)
            _body(ws, current, len(columns) + 3, _weighted_average(student_grades), bold=True, fill=TOTAL_FILL)
        if students:
            total_row = first_data + len(students)
            _body(ws, total_row, 1, "", fill=TOTAL_FILL)
            _body(ws, total_row, 2, "Promedio del curso", center=False, bold=True, fill=TOTAL_FILL)
            for index, (title, _, _, evaluation_id) in enumerate(columns, start=3):
                scores = []
                for student in students:
                    student_grades = by_student_subject.get((student.id, assignment.subject_id), [])
                    grade = (
                        next((g for g in student_grades if g.evaluation_id == evaluation_id), None)
                        if evaluation_id
                        else next((g for g in student_grades if g.evaluation_id is None and g.title == title), None)
                    )
                    if grade:
                        scores.append(float(grade.score))
                _body(ws, total_row, index, _mean(scores), bold=True, fill=TOTAL_FILL)
            _body(ws, total_row, len(columns) + 3, "", fill=TOTAL_FILL)
        _widths(ws, [14, 34] + [13] * len(columns) + [15])
        ws.freeze_panes = f"C{first_data}"

    return _xlsx(wb, f"planilla-notas-{_slug(course.name)}-{course.year}.xlsx")


@router.get("/courses/{course_id}/attendance.xlsx")
def attendance_sheet(
    course_id: int,
    month: str | None = Query(None, description="Mes en formato AAAA-MM"),
    db: Session = Depends(get_db),
):
    """Libro de asistencia mensual: un casillero por día, con resumen por estudiante."""
    course = _course_or_404(db, course_id)
    if month is None:
        today = DateType.today()
        month = f"{today.year}-{today.month:02d}"
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(422, "El mes debe tener el formato AAAA-MM")
    year, month_number = int(month[:4]), int(month[5:])
    days = monthrange(year, month_number)[1]
    first, last = DateType(year, month_number, 1), DateType(year, month_number, days)

    students = _students(db, course.id)
    records = list(
        db.scalars(
            select(Attendance).where(
                Attendance.course_id == course.id,
                Attendance.date >= first,
                Attendance.date <= last,
            )
        ).all()
    )
    by_student: dict[int, dict[int, str]] = defaultdict(dict)
    for record in records:
        by_student[record.student_id][record.date.day] = record.status

    weekdays = ["L", "M", "X", "J", "V", "S", "D"]
    headers = ["RUT", "Estudiante"] + [str(day) for day in range(1, days + 1)] + ["P", "A", "T", "J", "% Asist."]
    wb = Workbook()
    ws = _sheet(wb, f"Asistencia {month}")
    row = _title_block(
        ws,
        f"Libro de asistencia · {course.name}",
        [
            f"Mes {month} · Año {course.year}",
            "P = presente · T = atrasado · A = ausente · J = justificado · casillero vacío = sin registro",
        ],
        len(headers),
    )
    _header(ws, row, headers)
    weekday_row = row + 1
    _body(ws, weekday_row, 1, "", fill=TOTAL_FILL)
    _body(ws, weekday_row, 2, "", fill=TOTAL_FILL)
    for day in range(1, days + 1):
        _body(
            ws,
            weekday_row,
            2 + day,
            weekdays[DateType(year, month_number, day).weekday()],
            fill=TOTAL_FILL,
        )
    for col in range(days + 3, len(headers) + 1):
        _body(ws, weekday_row, col, "", fill=TOTAL_FILL)

    first_data = weekday_row + 1
    totals = dict.fromkeys(STATUS_LETTER, 0)
    for offset, student in enumerate(students):
        current = first_data + offset
        _body(ws, current, 1, student.rut, center=False)
        _body(ws, current, 2, student.full_name, center=False)
        counts = dict.fromkeys(STATUS_LETTER, 0)
        for day in range(1, days + 1):
            record_status = by_student.get(student.id, {}).get(day)
            if record_status:
                counts[record_status] += 1
                totals[record_status] += 1
            _body(
                ws,
                current,
                2 + day,
                STATUS_LETTER.get(record_status, "") if record_status else None,
                fill=STATUS_FILLS.get(record_status),
            )
        for index, key in enumerate(("presente", "ausente", "atrasado", "justificado"), start=days + 3):
            _body(ws, current, index, counts[key] if counts[key] else None)
        present = counts["presente"] + counts["atrasado"]
        marked = sum(counts.values())
        rate = round(present / marked * 100, 1) if marked else None
        _body(ws, current, len(headers), rate, bold=True)

    if students:
        total_row = first_data + len(students)
        _body(ws, total_row, 1, "", fill=TOTAL_FILL)
        _body(ws, total_row, 2, "Total del curso", center=False, bold=True, fill=TOTAL_FILL)
        for day in range(1, days + 1):
            _body(ws, total_row, 2 + day, "", fill=TOTAL_FILL)
        for index, key in enumerate(("presente", "ausente", "atrasado", "justificado"), start=days + 3):
            _body(ws, total_row, index, totals[key] or None, bold=True, fill=TOTAL_FILL)
        marked = sum(totals.values())
        present = totals["presente"] + totals["atrasado"]
        _body(
            ws,
            total_row,
            len(headers),
            round(present / marked * 100, 1) if marked else None,
            bold=True,
            fill=TOTAL_FILL,
        )

    _widths(ws, [14, 32] + [4] * days + [6, 6, 6, 6, 10])
    ws.freeze_panes = f"C{first_data}"
    return _xlsx(wb, f"asistencia-{_slug(course.name)}-{month}.xlsx")


@router.get("/courses/{course_id}/summary.xlsx")
def course_summary(
    course_id: int,
    _: object = Depends(require_management),
    db: Session = Depends(get_db),
):
    """Resumen del curso: promedio por asignatura, asistencia anual y deuda de cada estudiante."""
    course = _course_or_404(db, course_id)
    assignments = _assignments(db, course.id)
    students = _students(db, course.id)
    student_ids = [s.id for s in students]

    grades = list(
        db.scalars(select(Grade).where(Grade.course_id == course.id)).all()
    )
    by_student_subject: dict[tuple[int, int], list[Grade]] = defaultdict(list)
    for grade in grades:
        by_student_subject[(grade.student_id, grade.subject_id)].append(grade)

    year_start, year_end = DateType(course.year, 1, 1), DateType(course.year, 12, 31)
    attendance_by_student: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for record in db.scalars(
        select(Attendance).where(
            Attendance.student_id.in_(student_ids) if student_ids else Attendance.id.is_(None),
            Attendance.date >= year_start,
            Attendance.date <= year_end,
        )
    ).all():
        attendance_by_student[record.student_id][record.status] += 1

    fees = list(
        db.scalars(
            select(Fee)
            .options(selectinload(Fee.payments))
            .where(
                Fee.student_id.in_(student_ids) if student_ids else Fee.id.is_(None),
                Fee.period.like(f"{course.year}-%"),
            )
        ).all()
    )
    balance: dict[int, int] = defaultdict(int)
    overdue: dict[int, int] = defaultdict(int)
    for fee in fees:
        balance[fee.student_id] += fee.balance
        if fee.status == "vencida":
            overdue[fee.student_id] += fee.balance

    headers = (
        ["RUT", "Estudiante"]
        + [a.subject.name for a in assignments]
        + ["Promedio general", "% Asistencia", "Deuda total", "Deuda vencida"]
    )
    wb = Workbook()
    ws = _sheet(wb, "Resumen del curso")
    row = _title_block(
        ws,
        f"Resumen del curso · {course.name}",
        [
            f"Año {course.year}"
            + (f" · Profesor jefe: {course.head_teacher_name}" if course.head_teacher_name else "")
            + f" · {len(students)} estudiantes"
        ],
        len(headers),
    )
    _header(ws, row, headers)
    first_data = row + 1

    first_subject_col = 3
    overall_col = first_subject_col + len(assignments)
    attendance_col = overall_col + 1
    debt_col = overall_col + 2
    overdue_col = overall_col + 3

    for offset, student in enumerate(students):
        current = first_data + offset
        _body(ws, current, 1, student.rut, center=False)
        _body(ws, current, 2, student.full_name, center=False)
        averages = []
        for index, assignment in enumerate(assignments, start=first_subject_col):
            average = _weighted_average(
                by_student_subject.get((student.id, assignment.subject_id), [])
            )
            averages.append(average)
            _body(ws, current, index, average)
        _body(ws, current, overall_col, _mean(averages), bold=True, fill=TOTAL_FILL)
        counts = attendance_by_student.get(student.id, {})
        marked = sum(counts.values())
        present = counts.get("presente", 0) + counts.get("atrasado", 0)
        _body(ws, current, attendance_col, round(present / marked * 100, 1) if marked else None)
        _body(ws, current, debt_col, balance.get(student.id, 0) or None)
        _body(ws, current, overdue_col, overdue.get(student.id, 0) or None)

    if students:
        total_row = first_data + len(students)
        _body(ws, total_row, 1, "", fill=TOTAL_FILL)
        _body(ws, total_row, 2, "Total del curso", center=False, bold=True, fill=TOTAL_FILL)
        for index, assignment in enumerate(assignments, start=first_subject_col):
            _body(
                ws,
                total_row,
                index,
                _mean(
                    [
                        _weighted_average(
                            by_student_subject.get((s.id, assignment.subject_id), [])
                        )
                        for s in students
                    ]
                ),
                bold=True,
                fill=TOTAL_FILL,
            )
        _body(
            ws,
            total_row,
            overall_col,
            _mean(
                [
                    _mean(
                        [
                            _weighted_average(
                                by_student_subject.get((s.id, a.subject_id), [])
                            )
                            for a in assignments
                        ]
                    )
                    for s in students
                ]
            ),
            bold=True,
            fill=TOTAL_FILL,
        )
        all_counts: dict[str, int] = defaultdict(int)
        for counts in attendance_by_student.values():
            for key, value in counts.items():
                all_counts[key] += value
        marked = sum(all_counts.values())
        present = all_counts.get("presente", 0) + all_counts.get("atrasado", 0)
        _body(
            ws,
            total_row,
            attendance_col,
            round(present / marked * 100, 1) if marked else None,
            bold=True,
            fill=TOTAL_FILL,
        )
        _body(ws, total_row, debt_col, sum(balance.values()) or None, bold=True, fill=TOTAL_FILL)
        _body(ws, total_row, overdue_col, sum(overdue.values()) or None, bold=True, fill=TOTAL_FILL)

    _widths(ws, [14, 32] + [14] * len(assignments) + [15, 13, 13, 14])
    ws.freeze_panes = f"C{first_data}"
    return _xlsx(wb, f"resumen-{_slug(course.name)}-{course.year}.xlsx")


@router.get("/students/{student_id}/certificate")
def student_certificate(student_id: int, db: Session = Depends(get_db)):
    """Datos para el certificado de alumno regular (se imprime o guarda como PDF)."""
    student = db.scalar(
        select(Student)
        .options(joinedload(Student.course), joinedload(Student.guardian))
        .where(Student.id == student_id)
    )
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estudiante no encontrado")
    if not student.is_active:
        raise HTTPException(422, "El estudiante no está activo")

    course = student.course
    year = course.year if course else DateType.today().year
    counts = dict.fromkeys(("presente", "ausente", "atrasado", "justificado"), 0)
    for record in db.scalars(
        select(Attendance).where(
            Attendance.student_id == student.id,
            Attendance.date >= DateType(year, 1, 1),
            Attendance.date <= DateType(year, 12, 31),
        )
    ).all():
        counts[record.status] += 1
    marked = sum(counts.values())
    present = counts["presente"] + counts["atrasado"]

    grades = list(
        db.scalars(
            select(Grade).where(
                Grade.student_id == student.id,
                Grade.course_id == course.id if course else Grade.id.is_(None),
            )
        ).all()
    )
    by_subject: dict[int, list[Grade]] = defaultdict(list)
    for grade in grades:
        by_subject[grade.subject_id].append(grade)
    subject_averages = [_weighted_average(gs) for gs in by_subject.values()]
    overall = _mean(subject_averages)

    issued_on = DateType.today().isoformat()
    certificate_number = f"CERT-{year}-{student.id:04d}"
    signed_payload = {
        "certificate_number": certificate_number,
        "issued_on": issued_on,
        "student_name": student.full_name,
        "student_rut": student.rut,
        "course_name": course.name if course else None,
        "year": year,
    }
    signature = sign(signed_payload)
    code = code_for(signature)
    if db.scalar(
        select(CertificateSignature).where(CertificateSignature.code == code)
    ) is None:
        db.add(
            CertificateSignature(
                code=code,
                student_id=student.id,
                certificate_number=certificate_number,
                issued_on=DateType.today(),
                payload=canonical(signed_payload),
                signature=signature,
            )
        )
        db.commit()

    return {
        "certificate_number": certificate_number,
        "issued_on": issued_on,
        "signature": {
            "code": code,
            "algorithm": "HMAC-SHA256",
            "verification_url": f"/verificar/{code}",
        },
        "student": {
            "id": student.id,
            "full_name": student.full_name,
            "rut": student.rut,
            "birth_date": student.birth_date.isoformat(),
            "gender": student.gender,
            "enrollment_date": student.enrollment_date.isoformat() if student.enrollment_date else None,
            "status": student.status,
            "guardian_name": student.guardian.full_name if student.guardian else None,
        },
        "course": {
            "id": course.id if course else None,
            "name": course.name if course else None,
            "level": course.level if course else None,
            "year": year,
            "head_teacher_name": course.head_teacher_name if course else None,
        },
        "attendance": {
            "year": year,
            "marked": marked,
            "present": present,
            "rate": round(present / marked * 100, 1) if marked else None,
        },
        "grades": {
            "subjects": len(by_subject),
            "average": overall,
        },
    }
