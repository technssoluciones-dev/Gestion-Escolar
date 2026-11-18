from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CourseSubject, Grade, Subject
from ..schemas import Page, SubjectIn, SubjectOut
from ..security import require_management, require_staff

router = APIRouter(prefix="/subjects", tags=["Asignaturas"], dependencies=[Depends(require_staff)])


def _get_or_404(db: Session, subject_id: int) -> Subject:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asignatura no encontrada")
    return subject


def _duplicate_error() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, "Ya existe una asignatura con ese nombre")


def _check_name_free(db: Session, name: str, exclude_id: int | None = None) -> None:
    found = db.scalar(select(Subject).where(func.lower(Subject.name) == name.lower()))
    if found and found.id != exclude_id:
        raise _duplicate_error()


@router.get("", response_model=Page[SubjectOut])
def list_subjects(
    q: str | None = None,
    skip: int = 0,
    limit: int = Query(100, le=200),
    db: Session = Depends(get_db),
):
    query = select(Subject)
    if q:
        query = query.where(Subject.name.ilike(f"%{q.strip()}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Subject.name).offset(skip).limit(limit)).all()
    return {"items": items, "total": total}


@router.post(
    "",
    response_model=SubjectOut,
    status_code=201,
    dependencies=[Depends(require_management)],
)
def create_subject(data: SubjectIn, db: Session = Depends(get_db)):
    _check_name_free(db, data.name)
    subject = Subject(**data.model_dump())
    db.add(subject)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate_error()
    db.refresh(subject)
    return subject


@router.get("/{subject_id}", response_model=SubjectOut)
def get_subject(subject_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, subject_id)


@router.put(
    "/{subject_id}",
    response_model=SubjectOut,
    dependencies=[Depends(require_management)],
)
def update_subject(subject_id: int, data: SubjectIn, db: Session = Depends(get_db)):
    subject = _get_or_404(db, subject_id)
    _check_name_free(db, data.name, exclude_id=subject.id)
    for key, value in data.model_dump().items():
        setattr(subject, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate_error()
    db.refresh(subject)
    return subject


@router.delete(
    "/{subject_id}", status_code=204, dependencies=[Depends(require_management)]
)
def delete_subject(subject_id: int, db: Session = Depends(get_db)):
    subject = _get_or_404(db, subject_id)
    if db.scalar(select(func.count(CourseSubject.id)).where(CourseSubject.subject_id == subject.id)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No se puede eliminar: la asignatura está asignada a un curso",
        )
    if db.scalar(select(func.count(Grade.id)).where(Grade.subject_id == subject.id)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No se puede eliminar: la asignatura tiene notas registradas",
        )
    db.delete(subject)
    db.commit()
