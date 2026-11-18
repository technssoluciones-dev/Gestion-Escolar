from datetime import date as DateType

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import (
    Admission,
    Attendance,
    Course,
    Fee,
    Guardian,
    Student,
    Subject,
    Teacher,
    User,
)
from ..schemas import DashboardOut
from ..security import require_staff

router = APIRouter(prefix="/dashboard", tags=["Panel"], dependencies=[Depends(require_staff)])


@router.get("", response_model=DashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    active = Student.is_active.is_(True)
    today = DateType.today()

    def count(stmt) -> int:
        return db.scalar(stmt) or 0

    per_course = db.execute(
        select(Course.name, func.count(Student.id))
        .select_from(Course)
        .outerjoin(Student, (Student.course_id == Course.id) & active)
        .group_by(Course.id)
        .order_by(Course.year.desc(), Course.name)
    ).all()

    students_with_course = count(
        select(func.count(Student.id)).where(active, Student.course_id.is_not(None))
    )
    attendance_counts = dict.fromkeys(
        ("presente", "ausente", "atrasado", "justificado"), 0
    )
    for status_, n in db.execute(
        select(Attendance.status, func.count(Attendance.id))
        .join(Student, Student.id == Attendance.student_id)
        .where(
            Attendance.date == today,
            Student.is_active.is_(True),
            Student.course_id.is_not(None),
        )
        .group_by(Attendance.status)
    ).all():
        if status_ in attendance_counts:
            attendance_counts[status_] = n
    marked = sum(attendance_counts.values())
    present = attendance_counts["presente"] + attendance_counts["atrasado"]

    fees_pending = 0
    fees_overdue = 0
    if user.role in ("admin", "secretaria"):
        fees = db.scalars(select(Fee).options(selectinload(Fee.payments))).all()
        fees_pending = sum(f.balance for f in fees if f.status != "vencida")
        fees_overdue = sum(f.balance for f in fees if f.status == "vencida")

    return {
        "students": count(select(func.count(Student.id)).where(active)),
        "teachers": count(select(func.count(Teacher.id)).where(Teacher.is_active.is_(True))),
        "guardians": count(select(func.count(Guardian.id))),
        "courses": count(select(func.count(Course.id))),
        "subjects": count(select(func.count(Subject.id))),
        "pending_admissions": count(
            select(func.count(Admission.id)).where(
                Admission.status.in_(("postulada", "en_revision"))
            )
        ),
        "students_without_course": count(
            select(func.count(Student.id)).where(active, Student.course_id.is_(None))
        ),
        "fees_pending": fees_pending,
        "fees_overdue": fees_overdue,
        "attendance_today": {
            "date": today,
            "marked": marked,
            **attendance_counts,
            "unmarked": max(students_with_course - marked, 0),
            "rate": round(present / marked * 100, 1) if marked else None,
        },
        "per_course": [{"course": name, "students": n} for name, n in per_course],
    }
