from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Course, Guardian, Student
from ..rut import normalize_rut
from ..schemas import Page, StudentIn, StudentOut
from ..security import current_user

router = APIRouter(prefix="/students", tags=["Estudiantes"], dependencies=[Depends(current_user)])


def _check_relations(db: Session, data: StudentIn) -> None:
    if data.course_id is not None and db.get(Course, data.course_id) is None:
        raise HTTPException(422, "El curso indicado no existe")
    if data.guardian_id is not None and db.get(Guardian, data.guardian_id) is None:
        raise HTTPException(422, "El apoderado indicado no existe")


def _check_rut_free(db: Session, rut: str, exclude_id: int | None = None) -> None:
    found = db.scalar(select(Student).where(Student.rut == rut))
    if found and found.id != exclude_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un estudiante con ese RUT")


@router.get("", response_model=Page[StudentOut])
def list_students(
    q: str | None = None,
    course_id: int | None = None,
    status_: str | None = Query(None, alias="status"),
    skip: int = 0,
    limit: int = Query(20, le=200),
    db: Session = Depends(get_db),
):
    query = select(Student).where(Student.is_active.is_(True))
    if q:
        like = f"%{q.strip()}%"
        conditions = [Student.first_name.ilike(like), Student.last_name.ilike(like)]
        try:
            conditions.append(Student.rut == normalize_rut(q))
        except ValueError:
            pass
        query = query.where(or_(*conditions))
    if course_id is not None:
        query = query.where(Student.course_id == course_id)
    if status_:
        query = query.where(Student.status == status_)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(joinedload(Student.course), joinedload(Student.guardian))
        .order_by(Student.last_name, Student.first_name)
        .offset(skip)
        .limit(limit)
    ).all()
    return {"items": items, "total": total}


@router.post("", response_model=StudentOut, status_code=201)
def create_student(data: StudentIn, db: Session = Depends(get_db)):
    _check_rut_free(db, data.rut)
    _check_relations(db, data)
    student = Student(**data.model_dump())
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


def _get_or_404(db: Session, student_id: int) -> Student:
    student = db.get(Student, student_id)
    if student is None or not student.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estudiante no encontrado")
    return student


@router.get("/{student_id}", response_model=StudentOut)
def get_student(student_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, student_id)


@router.put("/{student_id}", response_model=StudentOut)
def update_student(student_id: int, data: StudentIn, db: Session = Depends(get_db)):
    student = _get_or_404(db, student_id)
    _check_rut_free(db, data.rut, exclude_id=student.id)
    _check_relations(db, data)
    for key, value in data.model_dump().items():
        setattr(student, key, value)
    db.commit()
    db.refresh(student)
    return student


@router.delete("/{student_id}", status_code=204)
def delete_student(student_id: int, db: Session = Depends(get_db)):
    """No borra el registro: lo marca como inactivo (se conserva el historial)."""
    student = _get_or_404(db, student_id)
    student.is_active = False
    student.status = "retirado"
    db.commit()
