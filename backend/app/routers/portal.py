from collections import defaultdict
from datetime import date as DateType
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..database import get_db
from ..models import Attendance, Fee, Grade, Guardian, Notification, Student, User
from ..schemas import (
    FeeOut,
    GradeOut,
    NotificationOut,
    PortalAttendanceOut,
    PortalMeOut,
    PortalOverviewOut,
    PortalStudentOut,
    PortalSubjectRow,
)
from ..security import require_portal

router = APIRouter(prefix="/portal", tags=["Portal"])


def _student_query():
    return select(Student).options(joinedload(Student.course))


@router.get("/me", response_model=PortalMeOut)
def portal_me(
    user: User = Depends(require_portal), db: Session = Depends(get_db)
):
    guardian = db.get(Guardian, user.guardian_id) if user.guardian_id else None
    student = (
        db.scalar(_student_query().where(Student.id == user.student_id))
        if user.student_id
        else None
    )
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "guardian": guardian,
        "student": student,
    }


@router.get("/children", response_model=list[PortalStudentOut])
def portal_children(
    user: User = Depends(require_portal), db: Session = Depends(get_db)
):
    if user.role == "estudiante":
        student = (
            db.scalar(_student_query().where(Student.id == user.student_id))
            if user.student_id
            else None
        )
        return [student] if student else []
    if user.guardian_id is None:
        return []
    return list(
        db.scalars(
            _student_query()
            .where(
                Student.guardian_id == user.guardian_id,
                Student.is_active.is_(True),
            )
            .order_by(Student.last_name, Student.first_name)
        ).all()
    )


@router.get("/notifications", response_model=list[NotificationOut])
def portal_notifications(
    student_id: int | None = None,
    user: User = Depends(require_portal),
    db: Session = Depends(get_db),
):
    """Avisos ya enviados por el colegio a la familia."""
    query = select(Notification).options(
        joinedload(Notification.student).joinedload(Student.course),
        joinedload(Notification.guardian),
    ).where(Notification.status == "enviada")
    if student_id is not None:
        student = _allowed_student(db, user, student_id)
        query = query.where(Notification.student_id == student.id)
    elif user.role == "estudiante":
        if user.student_id is None:
            return []
        query = query.where(Notification.student_id == user.student_id)
    else:
        if user.guardian_id is None:
            return []
        query = query.join(Student, Student.id == Notification.student_id).where(
            Student.guardian_id == user.guardian_id
        )
    return db.scalars(
        query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(50)
    ).all()


def _allowed_student(db: Session, user: User, student_id: int) -> Student:
    student = db.scalar(_student_query().where(Student.id == student_id))
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estudiante no encontrado")
    if user.role == "estudiante" and user.student_id == student.id:
        return student
    if (
        user.role == "apoderado"
        and user.guardian_id is not None
        and student.guardian_id == user.guardian_id
    ):
        return student
    raise HTTPException(
        status.HTTP_403_FORBIDDEN, "No puedes ver la información de este estudiante"
    )


def _weighted_average(grades: list[Grade]) -> float | None:
    total_weight = sum(grade.weight for grade in grades)
    if not total_weight:
        return None
    return round(
        sum(float(grade.score) * grade.weight for grade in grades) / total_weight, 1
    )


@router.get("/students/{student_id}", response_model=PortalOverviewOut)
def portal_student_overview(
    student_id: int,
    user: User = Depends(require_portal),
    db: Session = Depends(get_db),
):
    student = _allowed_student(db, user, student_id)

    to_date = DateType.today()
    from_date = to_date - timedelta(days=60)
    records = db.scalars(
        select(Attendance)
        .where(
            Attendance.student_id == student.id,
            Attendance.date >= from_date,
            Attendance.date <= to_date,
        )
        .order_by(Attendance.date)
    ).all()
    counts = defaultdict(int)
    for record in records:
        counts[record.status] += 1
    total = len(records)
    attended = counts["presente"] + counts["atrasado"]
    attendance = PortalAttendanceOut(
        from_date=from_date,
        to_date=to_date,
        total=total,
        presente=counts["presente"],
        ausente=counts["ausente"],
        atrasado=counts["atrasado"],
        justificado=counts["justificado"],
        rate=round(attended / total * 100, 1) if total else None,
    )

    grades = db.scalars(
        select(Grade)
        .options(joinedload(Grade.subject))
        .where(Grade.student_id == student.id)
        .order_by(Grade.subject_id, Grade.date.desc(), Grade.id.desc())
    ).all()
    by_subject: dict[int, list[Grade]] = defaultdict(list)
    for grade in grades:
        by_subject[grade.subject_id].append(grade)
    subjects: list[PortalSubjectRow] = []
    for subject_grades in by_subject.values():
        subject = subject_grades[0].subject
        subjects.append(
            PortalSubjectRow(
                subject=subject,
                grades=[GradeOut.model_validate(g) for g in subject_grades],
                average=_weighted_average(subject_grades),
                count=len(subject_grades),
            )
        )
    subjects.sort(key=lambda row: row.subject.name)
    averages = [row.average for row in subjects if row.average is not None]
    overall = round(sum(averages) / len(averages), 1) if averages else None

    fees = db.scalars(
        select(Fee)
        .options(
            joinedload(Fee.student).joinedload(Student.course),
            selectinload(Fee.payments),
        )
        .where(Fee.student_id == student.id)
        .order_by(Fee.due_date.desc(), Fee.id.desc())
    ).all()

    return {
        "student": student,
        "attendance": attendance,
        "subjects": subjects,
        "overall": overall,
        "fees": [FeeOut.model_validate(fee) for fee in fees],
        "pending_amount": sum(fee.balance for fee in fees),
        "overdue_amount": sum(
            fee.balance for fee in fees if fee.status == "vencida"
        ),
    }
