from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Guardian
from ..rut import normalize_rut
from ..schemas import GuardianIn, GuardianOut, Page
from ..security import current_user

router = APIRouter(prefix="/guardians", tags=["Apoderados"], dependencies=[Depends(current_user)])


def _check_rut_free(db: Session, rut: str, exclude_id: int | None = None) -> None:
    found = db.scalar(select(Guardian).where(Guardian.rut == rut))
    if found and found.id != exclude_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un apoderado con ese RUT")


def _get_or_404(db: Session, guardian_id: int) -> Guardian:
    guardian = db.get(Guardian, guardian_id)
    if guardian is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Apoderado no encontrado")
    return guardian


@router.get("", response_model=Page[GuardianOut])
def list_guardians(
    q: str | None = None,
    skip: int = 0,
    limit: int = Query(20, le=200),
    db: Session = Depends(get_db),
):
    query = select(Guardian)
    if q:
        like = f"%{q.strip()}%"
        conditions = [Guardian.first_name.ilike(like), Guardian.last_name.ilike(like)]
        try:
            conditions.append(Guardian.rut == normalize_rut(q))
        except ValueError:
            pass
        query = query.where(or_(*conditions))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(Guardian.last_name, Guardian.first_name).offset(skip).limit(limit)
    ).all()
    return {"items": items, "total": total}


@router.post("", response_model=GuardianOut, status_code=201)
def create_guardian(data: GuardianIn, db: Session = Depends(get_db)):
    _check_rut_free(db, data.rut)
    guardian = Guardian(**data.model_dump())
    db.add(guardian)
    db.commit()
    db.refresh(guardian)
    return guardian


@router.get("/{guardian_id}", response_model=GuardianOut)
def get_guardian(guardian_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, guardian_id)


@router.put("/{guardian_id}", response_model=GuardianOut)
def update_guardian(guardian_id: int, data: GuardianIn, db: Session = Depends(get_db)):
    guardian = _get_or_404(db, guardian_id)
    _check_rut_free(db, data.rut, exclude_id=guardian.id)
    for key, value in data.model_dump().items():
        setattr(guardian, key, value)
    db.commit()
    db.refresh(guardian)
    return guardian


@router.delete("/{guardian_id}", status_code=204)
def delete_guardian(guardian_id: int, db: Session = Depends(get_db)):
    guardian = _get_or_404(db, guardian_id)
    for student in guardian.students:  # Los alumnos quedan sin apoderado asignado
        student.guardian_id = None
    db.delete(guardian)
    db.commit()
