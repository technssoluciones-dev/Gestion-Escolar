from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from ..database import get_db
from ..models import CourseSubject, Evaluation
from ..schemas import EvaluationIn, EvaluationOut, Page
from ..security import require_staff

router = APIRouter(
    prefix="/evaluations", tags=["Evaluaciones"], dependencies=[Depends(require_staff)]
)


def _evaluation_options():
    return (
        joinedload(Evaluation.course_subject).joinedload(CourseSubject.course),
        joinedload(Evaluation.course_subject).joinedload(CourseSubject.subject),
        joinedload(Evaluation.course_subject).joinedload(CourseSubject.teacher),
        selectinload(Evaluation.grades),
    )


def _get_evaluation(db: Session, evaluation_id: int) -> Evaluation:
    evaluation = db.scalar(
        select(Evaluation)
        .options(*_evaluation_options())
        .where(Evaluation.id == evaluation_id)
    )
    if evaluation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluación no encontrada")
    return evaluation


def _course_subject_or_404(db: Session, course_subject_id: int) -> CourseSubject:
    course_subject = db.scalar(
        select(CourseSubject)
        .options(
            joinedload(CourseSubject.course),
            joinedload(CourseSubject.subject),
            joinedload(CourseSubject.teacher),
        )
        .where(CourseSubject.id == course_subject_id)
    )
    if course_subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asignatura del curso no encontrada")
    return course_subject


def _duplicate_error() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        "Ya existe una evaluación con ese nombre en esa asignatura del curso",
    )


def _check_duplicate(
    db: Session, course_subject_id: int, title: str, exclude_id: int | None = None
) -> None:
    query = select(Evaluation.id).where(
        Evaluation.course_subject_id == course_subject_id,
        func.lower(Evaluation.title) == title.lower(),
    )
    if exclude_id is not None:
        query = query.where(Evaluation.id != exclude_id)
    if db.scalar(query) is not None:
        raise _duplicate_error()


@router.get("", response_model=Page[EvaluationOut])
def list_evaluations(
    course_id: int | None = None,
    subject_id: int | None = None,
    course_subject_id: int | None = None,
    skip: int = 0,
    limit: int = Query(200, le=200),
    db: Session = Depends(get_db),
):
    query = select(Evaluation).join(Evaluation.course_subject)
    if course_id is not None:
        query = query.where(CourseSubject.course_id == course_id)
    if subject_id is not None:
        query = query.where(CourseSubject.subject_id == subject_id)
    if course_subject_id is not None:
        query = query.where(Evaluation.course_subject_id == course_subject_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(*_evaluation_options())
        .order_by(Evaluation.date.desc(), Evaluation.id.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return {"items": items, "total": total}


@router.post("", response_model=EvaluationOut, status_code=201)
def create_evaluation(data: EvaluationIn, db: Session = Depends(get_db)):
    _course_subject_or_404(db, data.course_subject_id)
    _check_duplicate(db, data.course_subject_id, data.title)
    evaluation = Evaluation(**data.model_dump())
    db.add(evaluation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate_error()
    return _get_evaluation(db, evaluation.id)


@router.put("/{evaluation_id}", response_model=EvaluationOut)
def update_evaluation(
    evaluation_id: int, data: EvaluationIn, db: Session = Depends(get_db)
):
    evaluation = _get_evaluation(db, evaluation_id)
    _course_subject_or_404(db, data.course_subject_id)
    if evaluation.grades and data.course_subject_id != evaluation.course_subject_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No se puede cambiar de curso o asignatura una evaluación con notas",
        )
    _check_duplicate(db, data.course_subject_id, data.title, exclude_id=evaluation.id)
    for key, value in data.model_dump().items():
        setattr(evaluation, key, value)
    # Las notas ya registradas siguen la definición de la evaluación.
    for grade in evaluation.grades:
        grade.title = evaluation.title
        grade.date = evaluation.date
        grade.weight = evaluation.weight
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate_error()
    db.expire_all()
    return _get_evaluation(db, evaluation.id)


@router.delete("/{evaluation_id}", status_code=204)
def delete_evaluation(evaluation_id: int, db: Session = Depends(get_db)):
    evaluation = _get_evaluation(db, evaluation_id)
    if evaluation.grades:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La evaluación tiene notas registradas; elimínalas primero",
        )
    db.delete(evaluation)
    db.commit()
