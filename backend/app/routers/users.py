from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Guardian, Student, Teacher, User
from ..schemas import Page, UserIn, UserOut, UserUpdate
from ..security import hash_password, require_admin, require_roles

router = APIRouter(
    prefix="/users", tags=["Usuarios"], dependencies=[Depends(require_admin)]
)


def _get_or_404(db: Session, user_id: int) -> User:
    user = db.scalar(
        select(User)
        .options(
            joinedload(User.guardian),
            joinedload(User.student),
            joinedload(User.teacher),
        )
        .where(User.id == user_id)
    )
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return user


def _check_email_free(db: Session, email: str, exclude_id: int | None = None) -> None:
    found = db.scalar(select(User).where(User.email == email))
    if found and found.id != exclude_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese correo")


def _check_links(
    db: Session,
    role: str,
    guardian_id: int | None,
    student_id: int | None,
    teacher_id: int | None,
) -> None:
    if guardian_id is not None and db.get(Guardian, guardian_id) is None:
        raise HTTPException(422, "El apoderado indicado no existe")
    if student_id is not None and db.get(Student, student_id) is None:
        raise HTTPException(422, "El estudiante indicado no existe")
    if teacher_id is not None and db.get(Teacher, teacher_id) is None:
        raise HTTPException(422, "El profesor indicado no existe")
    if role == "apoderado" and guardian_id is None:
        raise HTTPException(422, "Un usuario apoderado debe estar asociado a un apoderado")
    if role == "estudiante" and student_id is None:
        raise HTTPException(422, "Un usuario estudiante debe estar asociado a un estudiante")


@router.get("", response_model=Page[UserOut])
def list_users(
    q: str | None = None,
    role: str | None = None,
    skip: int = 0,
    limit: int = Query(100, le=200),
    db: Session = Depends(get_db),
):
    query = select(User)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(User.full_name.ilike(like), User.email.ilike(like))
        )
    if role:
        query = query.where(User.role == role)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(
            joinedload(User.guardian),
            joinedload(User.student),
            joinedload(User.teacher),
        )
        .order_by(User.full_name)
        .offset(skip)
        .limit(limit)
    ).all()
    return {"items": items, "total": total}


@router.post("", response_model=UserOut, status_code=201)
def create_user(data: UserIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    _check_email_free(db, email)
    _check_links(db, data.role, data.guardian_id, data.student_id, data.teacher_id)
    user = User(
        email=email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=data.role,
        is_active=data.is_active,
        guardian_id=data.guardian_id,
        student_id=data.student_id,
        teacher_id=data.teacher_id,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese correo")
    return _get_or_404(db, user.id)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, user_id)


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("admin")),
):
    user = _get_or_404(db, user_id)
    changes = data.model_dump(exclude_unset=True)
    password = changes.pop("password", None)

    if user.id == current.id:
        if changes.get("is_active") is False:
            raise HTTPException(409, "No puedes desactivar tu propio usuario")
        if changes.get("role", user.role) != "admin":
            raise HTTPException(409, "No puedes cambiar tu propio rol de administrador")

    if "email" in changes:
        changes["email"] = str(changes["email"]).lower()
        _check_email_free(db, changes["email"], exclude_id=user.id)

    role = changes.get("role", user.role)
    guardian_id = changes.get("guardian_id", user.guardian_id)
    student_id = changes.get("student_id", user.student_id)
    teacher_id = changes.get("teacher_id", user.teacher_id)
    _check_links(db, role, guardian_id, student_id, teacher_id)

    for key, value in changes.items():
        setattr(user, key, value)
    if password:
        user.hashed_password = hash_password(password)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese correo")
    db.expire_all()
    return _get_or_404(db, user.id)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("admin")),
):
    user = _get_or_404(db, user_id)
    if user.id == current.id:
        raise HTTPException(409, "No puedes eliminar tu propio usuario")
    db.delete(user)
    db.commit()
