from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Teacher
from ..rut import normalize_rut
from ..schemas import Page, TeacherIn, TeacherOut
from ..security import current_user

router = APIRouter(prefix="/teachers", tags=["Profesores"], dependencies=[Depends(current_user)])


def _check_rut_free(db: Session, rut: str, exclude_id: int | None = None) -> None:
    found = db.scalar(select(Teacher).where(Teacher.rut == rut))
    if found and found.id != exclude_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un profesor con ese RUT")


def _get_or_404(db: Session, teacher_id: int) -> Teacher:
    teacher = db.get(Teacher, teacher_id)
    if teacher is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profesor no encontrado")
    return teacher


@router.get("", response_model=Page[TeacherOut])
def list_teachers(
    q: str | None = None,
    skip: int = 0,
    limit: int = Query(20, le=200),
    db: Session = Depends(get_db),
):
    query = select(Teacher)
    if q:
        like = f"%{q.strip()}%"
        conditions = [Teacher.first_name.ilike(like), Teacher.last_name.ilike(like)]
        try:
            conditions.append(Teacher.rut == normalize_rut(q))
        except ValueError:
            pass
        query = query.where(or_(*conditions))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(selectinload(Teacher.head_courses))
        .order_by(Teacher.last_name, Teacher.first_name)
        .offset(skip)
        .limit(limit)
    ).all()
    return {"items": items, "total": total}


@router.post("", response_model=TeacherOut, status_code=201)
def create_teacher(data: TeacherIn, db: Session = Depends(get_db)):
    _check_rut_free(db, data.rut)
    teacher = Teacher(**data.model_dump())
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.get("/{teacher_id}", response_model=TeacherOut)
def get_teacher(teacher_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, teacher_id)


@router.put("/{teacher_id}", response_model=TeacherOut)
def update_teacher(teacher_id: int, data: TeacherIn, db: Session = Depends(get_db)):
    teacher = _get_or_404(db, teacher_id)
    _check_rut_free(db, data.rut, exclude_id=teacher.id)
    for key, value in data.model_dump().items():
        setattr(teacher, key, value)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.delete("/{teacher_id}", status_code=204)
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    teacher = _get_or_404(db, teacher_id)
    for course in teacher.head_courses:  # El curso queda sin profesor jefe
        course.head_teacher_id = None
    db.delete(teacher)
    db.commit()
