from collections import defaultdict
from datetime import date as DateType

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Attendance, Course, Student
from ..schemas import (
    AttendanceDayIn,
    AttendanceDayOut,
    AttendanceDaySummary,
    AttendancePeriodSummary,
    AttendanceRowOut,
    AttendanceSummaryOut,
    AttendanceSummaryRow,
)
from ..security import require_staff

router = APIRouter(prefix="/attendance", tags=["Asistencia"], dependencies=[Depends(require_staff)])

STATUSES = ("presente", "ausente", "atrasado", "justificado")


def _course_or_404(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curso no encontrado")
    return course


def _active_students(db: Session, course_id: int) -> list[Student]:
    return list(
        db.scalars(
            select(Student)
            .where(Student.course_id == course_id, Student.is_active.is_(True))
            .order_by(Student.last_name, Student.first_name)
        ).all()
    )


def _rate(present: int, total: int) -> float | None:
    return round(present / total * 100, 1) if total else None


def _day_payload(db: Session, course: Course, day: DateType) -> AttendanceDayOut:
    students = _active_students(db, course.id)
    records = {
        r.student_id: r
        for r in db.scalars(
            select(Attendance).where(Attendance.course_id == course.id, Attendance.date == day)
        ).all()
    }
    items = []
    counts = dict.fromkeys(STATUSES, 0)
    unmarked = 0
    for student in students:
        record = records.get(student.id)
        if record:
            counts[record.status] += 1
        else:
            unmarked += 1
        items.append(
            AttendanceRowOut(
                student_id=student.id,
                full_name=student.full_name,
                rut=student.rut,
                status=record.status if record else None,
                note=record.note if record else None,
                record_id=record.id if record else None,
            )
        )
    summary = AttendanceDaySummary(**counts, sin_marcar=unmarked)
    return AttendanceDayOut(course=course, date=day, items=items, summary=summary)


@router.get("/day", response_model=AttendanceDayOut)
def get_day(
    course_id: int,
    date: DateType | None = None,
    db: Session = Depends(get_db),
):
    """Estado de asistencia de un curso en un día, con todos sus estudiantes."""
    course = _course_or_404(db, course_id)
    return _day_payload(db, course, date or DateType.today())


@router.put("/day", response_model=AttendanceDayOut)
def save_day(data: AttendanceDayIn, db: Session = Depends(get_db)):
    """Guarda (o corrige) la asistencia del día. Enviar status vacío borra la marca."""
    course = _course_or_404(db, data.course_id)
    students = _active_students(db, course.id)
    active_ids = {s.id for s in students}

    seen: set[int] = set()
    for item in data.items:
        if item.student_id in seen:
            raise HTTPException(422, "Hay estudiantes repetidos en la lista de asistencia")
        seen.add(item.student_id)
        if item.student_id not in active_ids:
            raise HTTPException(422, "Uno de los estudiantes no pertenece al curso indicado")

    existing_conditions = [Attendance.date == data.date]
    if active_ids:
        existing_conditions.append(Attendance.student_id.in_(active_ids))
    else:
        existing_conditions.append(Attendance.student_id.is_(None))
    existing = {
        r.student_id: r
        for r in db.scalars(select(Attendance).where(*existing_conditions)).all()
    }

    for item in data.items:
        record = existing.get(item.student_id)
        if item.status is None:
            if record:
                db.delete(record)
            continue
        note = (item.note or "").strip() or None
        if record:
            record.status = item.status
            record.note = note
            record.course_id = course.id
        else:
            db.add(
                Attendance(
                    student_id=item.student_id,
                    course_id=course.id,
                    date=data.date,
                    status=item.status,
                    note=note,
                )
            )
    db.commit()
    return _day_payload(db, course, data.date)


@router.get("/summary", response_model=AttendanceSummaryOut)
def get_summary(
    course_id: int,
    from_date: DateType | None = Query(None, alias="from"),
    to_date: DateType | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    """Resumen de asistencia por estudiante en un rango de fechas."""
    course = _course_or_404(db, course_id)
    today = DateType.today()
    from_date = from_date or today.replace(day=1)
    to_date = to_date or today
    if from_date > to_date:
        raise HTTPException(422, "La fecha de inicio no puede ser posterior a la fecha de término")

    students = _active_students(db, course.id)
    by_student: dict[int, list[Attendance]] = defaultdict(list)
    for record in db.scalars(
        select(Attendance).where(
            Attendance.course_id == course.id,
            Attendance.date >= from_date,
            Attendance.date <= to_date,
        )
    ).all():
        by_student[record.student_id].append(record)

    items = []
    totals = dict.fromkeys(STATUSES, 0)
    days: set[DateType] = set()
    for student in students:
        records = by_student.get(student.id, [])
        counts = {s: sum(1 for r in records if r.status == s) for s in STATUSES}
        total = len(records)
        present = counts["presente"] + counts["atrasado"]
        for key in STATUSES:
            totals[key] += counts[key]
        days.update(r.date for r in records)
        items.append(
            AttendanceSummaryRow(
                student_id=student.id,
                full_name=student.full_name,
                rut=student.rut,
                **counts,
                total=total,
                rate=_rate(present, total),
            )
        )

    total = sum(totals.values())
    summary = AttendancePeriodSummary(
        **totals,
        total=total,
        rate=_rate(totals["presente"] + totals["atrasado"], total),
    )
    return AttendanceSummaryOut(
        course=course,
        from_date=from_date,
        to_date=to_date,
        days=len(days),
        items=items,
        summary=summary,
    )
