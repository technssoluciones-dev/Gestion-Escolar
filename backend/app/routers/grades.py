from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Course, Evaluation, Grade, Student, Subject
from ..schemas import (
    GradeBulkIn,
    GradeBulkOut,
    GradeIn,
    GradeMatrixOut,
    GradeOut,
    GradeReportOut,
    GradeSummary,
    Page,
    StudentGradeRow,
    StudentGradesOut,
    StudentMatrixRow,
    StudentSubjectRow,
    SubjectAverage,
)
from ..security import require_staff

router = APIRouter(prefix="/grades", tags=["Notas"], dependencies=[Depends(require_staff)])

APPROVAL = 4.0


def _course_or_404(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curso no encontrado")
    return course


def _subject_or_404(db: Session, subject_id: int) -> Subject:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asignatura no encontrada")
    return subject


def _student_or_404(db: Session, student_id: int) -> Student:
    student = db.get(Student, student_id)
    if student is None or not student.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estudiante no encontrado")
    return student


def _course_students(db: Session, course_id: int) -> list[Student]:
    return list(
        db.scalars(
            select(Student)
            .where(Student.course_id == course_id, Student.is_active.is_(True))
            .order_by(Student.last_name, Student.first_name)
        ).all()
    )


def _student_with_course(db: Session, student_id: int) -> Student:
    student = _student_or_404(db, student_id)
    if student.course_id is None:
        raise HTTPException(422, "El estudiante no tiene un curso asignado")
    return student


def _evaluation_for(
    db: Session, evaluation_id: int, course_id: int, subject_id: int
) -> Evaluation:
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(422, "La evaluación indicada no existe")
    course_subject = evaluation.course_subject
    if course_subject.course_id != course_id or course_subject.subject_id != subject_id:
        raise HTTPException(
            422, "La evaluación no corresponde a esa asignatura del curso"
        )
    return evaluation


def _weighted_average(grades: list[Grade]) -> float | None:
    total_weight = sum(g.weight for g in grades)
    if not total_weight:
        return None
    return round(sum(float(g.score) * g.weight for g in grades) / total_weight, 1)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _summary(averages: list[float | None], grade_count: int) -> GradeSummary:
    valid = [a for a in averages if a is not None]
    return GradeSummary(
        average=_mean(valid),
        approved=sum(1 for a in valid if a >= APPROVAL),
        failed=sum(1 for a in valid if a < APPROVAL),
        without_grades=sum(1 for a in averages if a is None),
        grade_count=grade_count,
    )


@router.get("", response_model=Page[GradeOut])
def list_grades(
    course_id: int | None = None,
    subject_id: int | None = None,
    student_id: int | None = None,
    skip: int = 0,
    limit: int = Query(100, le=200),
    db: Session = Depends(get_db),
):
    query = select(Grade)
    if course_id is not None:
        query = query.where(Grade.course_id == course_id)
    if subject_id is not None:
        query = query.where(Grade.subject_id == subject_id)
    if student_id is not None:
        query = query.where(Grade.student_id == student_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(Grade.date.desc(), Grade.id.desc()).offset(skip).limit(limit)
    ).all()
    return {"items": items, "total": total}


@router.post("", response_model=GradeOut, status_code=201)
def create_grade(data: GradeIn, db: Session = Depends(get_db)):
    student = _student_with_course(db, data.student_id)
    _subject_or_404(db, data.subject_id)
    values = data.model_dump()
    if data.evaluation_id is not None:
        evaluation = _evaluation_for(
            db, data.evaluation_id, student.course_id, data.subject_id
        )
        values.update(
            title=evaluation.title, date=evaluation.date, weight=evaluation.weight
        )
    grade = Grade(course_id=student.course_id, **values)
    db.add(grade)
    db.commit()
    db.refresh(grade)
    return grade


@router.post("/bulk", response_model=GradeBulkOut, status_code=201)
def create_grades_bulk(data: GradeBulkIn, db: Session = Depends(get_db)):
    """Registra la misma evaluación para varios estudiantes de un curso."""
    course = _course_or_404(db, data.course_id)
    _subject_or_404(db, data.subject_id)
    student_ids = {s.id for s in _course_students(db, course.id)}

    seen: set[int] = set()
    for item in data.items:
        if item.student_id in seen:
            raise HTTPException(422, "Hay estudiantes repetidos en la lista de notas")
        seen.add(item.student_id)
        if item.student_id not in student_ids:
            raise HTTPException(422, "Uno de los estudiantes no pertenece al curso indicado")

    evaluation = None
    title, grade_date, weight = data.title, data.date, data.weight
    if data.evaluation_id is not None:
        evaluation = _evaluation_for(db, data.evaluation_id, course.id, data.subject_id)
        title, grade_date, weight = evaluation.title, evaluation.date, evaluation.weight
        already_graded = db.scalars(
            select(Grade.student_id).where(
                Grade.evaluation_id == evaluation.id,
                Grade.student_id.in_(seen),
            )
        ).all()
        if already_graded:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Ya hay notas registradas para esa evaluación",
            )

    for item in data.items:
        db.add(
            Grade(
                student_id=item.student_id,
                subject_id=data.subject_id,
                course_id=course.id,
                title=title,
                score=item.score,
                weight=weight,
                date=grade_date,
                evaluation_id=evaluation.id if evaluation else None,
            )
        )
    db.commit()
    return {"created": len(data.items)}


@router.get("/report", response_model=GradeReportOut)
def grade_report(course_id: int, subject_id: int, db: Session = Depends(get_db)):
    """Notas y promedio de cada estudiante en una asignatura de un curso."""
    course = _course_or_404(db, course_id)
    subject = _subject_or_404(db, subject_id)
    grades = db.scalars(
        select(Grade)
        .where(Grade.course_id == course.id, Grade.subject_id == subject.id)
        .order_by(Grade.date, Grade.id)
    ).all()
    by_student: dict[int, list[Grade]] = defaultdict(list)
    for grade in grades:
        by_student[grade.student_id].append(grade)

    items = []
    for student in _course_students(db, course.id):
        student_grades = by_student.get(student.id, [])
        items.append(
            StudentGradeRow(
                student_id=student.id,
                full_name=student.full_name,
                rut=student.rut,
                grades=[GradeOut.model_validate(g) for g in student_grades],
                average=_weighted_average(student_grades),
                count=len(student_grades),
            )
        )
    return GradeReportOut(
        course=course,
        subject=subject,
        items=items,
        summary=_summary([i.average for i in items], len(grades)),
    )


@router.get("/matrix", response_model=GradeMatrixOut)
def grade_matrix(course_id: int, db: Session = Depends(get_db)):
    """Promedios por asignatura de todo un curso (una columna por asignatura)."""
    course = _course_or_404(db, course_id)
    students = _course_students(db, course.id)
    grades = db.scalars(select(Grade).where(Grade.course_id == course.id)).all()

    grouped: dict[tuple[int, int], list[Grade]] = defaultdict(list)
    for grade in grades:
        grouped[(grade.student_id, grade.subject_id)].append(grade)

    subject_ids = sorted({g.subject_id for g in grades})
    subjects = list(
        db.scalars(select(Subject).where(Subject.id.in_(subject_ids)).order_by(Subject.name)).all()
    ) if subject_ids else []

    rows = []
    for student in students:
        averages = []
        for subject in subjects:
            student_grades = grouped.get((student.id, subject.id), [])
            averages.append(
                SubjectAverage(
                    subject_id=subject.id,
                    average=_weighted_average(student_grades),
                    count=len(student_grades),
                )
            )
        rows.append(
            StudentMatrixRow(
                student_id=student.id,
                full_name=student.full_name,
                rut=student.rut,
                averages=averages,
                overall=_mean([a.average for a in averages if a.average is not None]),
            )
        )

    subject_averages = [
        SubjectAverage(
            subject_id=subject.id,
            average=_mean([row.averages[i].average for row in rows if row.averages[i].average is not None]),
            count=sum(row.averages[i].count for row in rows),
        )
        for i, subject in enumerate(subjects)
    ]
    return GradeMatrixOut(
        course=course,
        subjects=subjects,
        items=rows,
        subject_averages=subject_averages,
        summary=_summary([row.overall for row in rows], len(grades)),
    )


@router.get("/student/{student_id}", response_model=StudentGradesOut)
def student_grades(student_id: int, db: Session = Depends(get_db)):
    """Promedios por asignatura de un estudiante (su informe de notas)."""
    student = _student_or_404(db, student_id)
    grades = db.scalars(
        select(Grade)
        .where(Grade.student_id == student.id)
        .order_by(Grade.date, Grade.id)
    ).all()
    by_subject: dict[int, list[Grade]] = defaultdict(list)
    for grade in grades:
        by_subject[grade.subject_id].append(grade)

    subject_ids = list(by_subject)
    subjects = {
        s.id: s
        for s in db.scalars(select(Subject).where(Subject.id.in_(subject_ids))).all()
    } if subject_ids else {}

    items = [
        StudentSubjectRow(
            subject=subjects[subject_id],
            grades=[GradeOut.model_validate(g) for g in subject_grades],
            average=_weighted_average(subject_grades),
            count=len(subject_grades),
        )
        for subject_id, subject_grades in by_subject.items()
        if subject_id in subjects
    ]
    items.sort(key=lambda i: i.subject.name)
    return StudentGradesOut(
        student_id=student.id,
        full_name=student.full_name,
        rut=student.rut,
        items=items,
        overall=_mean([i.average for i in items if i.average is not None]),
    )


@router.put("/{grade_id}", response_model=GradeOut)
def update_grade(grade_id: int, data: GradeIn, db: Session = Depends(get_db)):
    grade = db.get(Grade, grade_id)
    if grade is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nota no encontrada")
    student = _student_with_course(db, data.student_id)
    _subject_or_404(db, data.subject_id)
    values = data.model_dump()
    if data.evaluation_id is not None:
        evaluation = _evaluation_for(
            db, data.evaluation_id, student.course_id, data.subject_id
        )
        values.update(
            title=evaluation.title, date=evaluation.date, weight=evaluation.weight
        )
    elif grade.evaluation_id is not None:
        # Mantiene el vínculo cuando la edición no envía evaluación.
        values["evaluation_id"] = grade.evaluation_id
    for key, value in values.items():
        setattr(grade, key, value)
    grade.course_id = student.course_id
    db.commit()
    db.refresh(grade)
    return grade


@router.delete("/{grade_id}", status_code=204)
def delete_grade(grade_id: int, db: Session = Depends(get_db)):
    grade = db.get(Grade, grade_id)
    if grade is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nota no encontrada")
    db.delete(grade)
    db.commit()
