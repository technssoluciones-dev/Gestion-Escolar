from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from ..database import get_db
from ..models import Attendance, Course, Grade, Teacher
from ..schemas import CourseIn, CourseOut, Page
from ..security import require_management, require_staff

router = APIRouter(prefix="/courses", tags=["Cursos"], dependencies=[Depends(require_staff)])


def _check_teacher(db: Session, teacher_id: int | None) -> None:
    if teacher_id is not None and db.get(Teacher, teacher_id) is None:
        raise HTTPException(422, "El profesor indicado no existe")


def _get_or_404(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curso no encontrado")
    return course


def _duplicate_error() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, "Ya existe un curso con ese nombre en ese año")


@router.get("", response_model=Page[CourseOut])
def list_courses(
    year: int | None = None,
    skip: int = 0,
    limit: int = Query(100, le=200),
    db: Session = Depends(get_db),
):
    query = select(Course)
    if year is not None:
        query = query.where(Course.year == year)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(joinedload(Course.head_teacher), selectinload(Course.students))
        .order_by(Course.year.desc(), Course.name)
        .offset(skip)
        .limit(limit)
    ).all()
    return {"items": items, "total": total}


@router.post(
    "",
    response_model=CourseOut,
    status_code=201,
    dependencies=[Depends(require_management)],
)
def create_course(data: CourseIn, db: Session = Depends(get_db)):
    _check_teacher(db, data.head_teacher_id)
    course = Course(**data.model_dump())
    db.add(course)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate_error()
    db.refresh(course)
    return course


@router.get("/{course_id}", response_model=CourseOut)
def get_course(course_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, course_id)


@router.put(
    "/{course_id}",
    response_model=CourseOut,
    dependencies=[Depends(require_management)],
)
def update_course(course_id: int, data: CourseIn, db: Session = Depends(get_db)):
    course = _get_or_404(db, course_id)
    _check_teacher(db, data.head_teacher_id)
    for key, value in data.model_dump().items():
        setattr(course, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate_error()
    db.refresh(course)
    return course


@router.delete(
    "/{course_id}", status_code=204, dependencies=[Depends(require_management)]
)
def delete_course(course_id: int, db: Session = Depends(get_db)):
    course = _get_or_404(db, course_id)
    has_attendance = db.scalar(
        select(func.count(Attendance.id)).where(Attendance.course_id == course.id)
    )
    has_grades = db.scalar(select(func.count(Grade.id)).where(Grade.course_id == course.id))
    if has_attendance or has_grades:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No se puede eliminar: el curso tiene asistencia o notas registradas",
        )
    for student in course.students:  # Los alumnos quedan sin curso asignado
        student.course_id = None
    db.delete(course)
    db.commit()
