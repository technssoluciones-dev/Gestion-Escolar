from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Course, Guardian, Student, Teacher
from ..schemas import DashboardOut
from ..security import current_user

router = APIRouter(prefix="/dashboard", tags=["Panel"], dependencies=[Depends(current_user)])


@router.get("", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db)):
    active = Student.is_active.is_(True)

    def count(stmt) -> int:
        return db.scalar(stmt) or 0

    per_course = db.execute(
        select(Course.name, func.count(Student.id))
        .select_from(Course)
        .outerjoin(Student, (Student.course_id == Course.id) & active)
        .group_by(Course.id)
        .order_by(Course.year.desc(), Course.name)
    ).all()

    return {
        "students": count(select(func.count(Student.id)).where(active)),
        "teachers": count(select(func.count(Teacher.id)).where(Teacher.is_active.is_(True))),
        "guardians": count(select(func.count(Guardian.id))),
        "courses": count(select(func.count(Course.id))),
        "students_without_course": count(
            select(func.count(Student.id)).where(active, Student.course_id.is_(None))
        ),
        "per_course": [{"course": name, "students": n} for name, n in per_course],
    }
