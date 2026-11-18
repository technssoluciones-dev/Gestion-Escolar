from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from ..database import get_db
from ..models import Course, CourseSubject, ScheduleBlock, Subject, Teacher
from ..schemas import CourseSubjectIn, CourseSubjectOut, Page, ScheduleIn, ScheduleOut
from ..security import require_management, require_staff

course_subject_router = APIRouter(
    prefix="/course-subjects", tags=["Horarios"], dependencies=[Depends(require_staff)]
)
schedule_router = APIRouter(
    prefix="/schedules", tags=["Horarios"], dependencies=[Depends(require_staff)]
)


def _course_or_404(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curso no encontrado")
    return course


def _subject_or_404(db: Session, subject_id: int) -> Subject:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asignatura no encontrada")
    return subject


def _check_teacher(db: Session, teacher_id: int | None) -> None:
    if teacher_id is not None and db.get(Teacher, teacher_id) is None:
        raise HTTPException(422, "El profesor indicado no existe")


def _get_course_subject(db: Session, course_subject_id: int) -> CourseSubject:
    course_subject = db.scalar(
        select(CourseSubject)
        .options(
            selectinload(CourseSubject.subject),
            selectinload(CourseSubject.teacher),
            selectinload(CourseSubject.schedules),
        )
        .where(CourseSubject.id == course_subject_id)
    )
    if course_subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asignatura del curso no encontrada")
    return course_subject


def _get_schedule(db: Session, schedule_id: int) -> ScheduleBlock:
    schedule = db.scalar(
        select(ScheduleBlock)
        .options(
            joinedload(ScheduleBlock.course_subject).joinedload(CourseSubject.subject),
            joinedload(ScheduleBlock.course_subject).joinedload(CourseSubject.teacher),
            joinedload(ScheduleBlock.course_subject).joinedload(CourseSubject.course),
        )
        .where(ScheduleBlock.id == schedule_id)
    )
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bloque de horario no encontrado")
    return schedule


def _duplicate_error() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT, "La asignatura ya está asignada a ese curso"
    )


def _validate_schedule(
    db: Session, course_subject: CourseSubject, data: ScheduleIn, exclude_id: int | None = None
) -> None:
    overlap = and_(
        ScheduleBlock.weekday == data.weekday,
        ScheduleBlock.start_time < data.end_time,
        ScheduleBlock.end_time > data.start_time,
    )

    def exists(*conditions) -> bool:
        query = (
            select(ScheduleBlock.id)
            .join(ScheduleBlock.course_subject)
            .where(overlap, *conditions)
        )
        if exclude_id is not None:
            query = query.where(ScheduleBlock.id != exclude_id)
        return db.scalar(query) is not None

    if exists(CourseSubject.course_id == course_subject.course_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El curso ya tiene una clase en ese horario"
        )

    if course_subject.teacher_id is not None and exists(
        CourseSubject.teacher_id == course_subject.teacher_id
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El profesor ya tiene una clase en ese horario"
        )

    if data.room and exists(func.lower(ScheduleBlock.room) == data.room.lower()):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "La sala ya está ocupada en ese horario"
        )


# ---------- Asignaturas por curso ----------
@course_subject_router.get("", response_model=Page[CourseSubjectOut])
def list_course_subjects(
    course_id: int | None = None,
    teacher_id: int | None = None,
    skip: int = 0,
    limit: int = Query(200, le=200),
    db: Session = Depends(get_db),
):
    query = select(CourseSubject).join(CourseSubject.subject)
    if course_id is not None:
        query = query.where(CourseSubject.course_id == course_id)
    if teacher_id is not None:
        query = query.where(CourseSubject.teacher_id == teacher_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(
            selectinload(CourseSubject.subject),
            selectinload(CourseSubject.teacher),
            selectinload(CourseSubject.schedules),
        )
        .order_by(Subject.name)
        .offset(skip)
        .limit(limit)
    ).all()
    return {"items": items, "total": total}


@course_subject_router.post(
    "",
    response_model=CourseSubjectOut,
    status_code=201,
    dependencies=[Depends(require_management)],
)
def create_course_subject(data: CourseSubjectIn, db: Session = Depends(get_db)):
    _course_or_404(db, data.course_id)
    _subject_or_404(db, data.subject_id)
    _check_teacher(db, data.teacher_id)
    duplicate = db.scalar(
        select(CourseSubject.id).where(
            CourseSubject.course_id == data.course_id,
            CourseSubject.subject_id == data.subject_id,
        )
    )
    if duplicate:
        raise _duplicate_error()
    course_subject = CourseSubject(**data.model_dump())
    db.add(course_subject)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate_error()
    return _get_course_subject(db, course_subject.id)


@course_subject_router.put(
    "/{course_subject_id}",
    response_model=CourseSubjectOut,
    dependencies=[Depends(require_management)],
)
def update_course_subject(
    course_subject_id: int, data: CourseSubjectIn, db: Session = Depends(get_db)
):
    course_subject = _get_course_subject(db, course_subject_id)
    _course_or_404(db, data.course_id)
    _subject_or_404(db, data.subject_id)
    _check_teacher(db, data.teacher_id)
    duplicate = db.scalar(
        select(CourseSubject.id).where(
            CourseSubject.course_id == data.course_id,
            CourseSubject.subject_id == data.subject_id,
            CourseSubject.id != course_subject.id,
        )
    )
    if duplicate:
        raise _duplicate_error()
    for key, value in data.model_dump().items():
        setattr(course_subject, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate_error()
    db.expire_all()  # recarga las relaciones (por ejemplo, el profesor cambió)
    return _get_course_subject(db, course_subject.id)


@course_subject_router.delete(
    "/{course_subject_id}", status_code=204, dependencies=[Depends(require_management)]
)
def delete_course_subject(course_subject_id: int, db: Session = Depends(get_db)):
    course_subject = _get_course_subject(db, course_subject_id)
    db.delete(course_subject)  # Los bloques de horario se eliminan en cascada
    db.commit()


# ---------- Bloques de horario ----------
@schedule_router.get("", response_model=list[ScheduleOut])
def list_schedules(
    course_id: int | None = None,
    teacher_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = select(ScheduleBlock).join(ScheduleBlock.course_subject)
    if course_id is not None:
        query = query.where(CourseSubject.course_id == course_id)
    if teacher_id is not None:
        query = query.where(CourseSubject.teacher_id == teacher_id)
    return db.scalars(
        query.options(
            joinedload(ScheduleBlock.course_subject).joinedload(CourseSubject.subject),
            joinedload(ScheduleBlock.course_subject).joinedload(CourseSubject.teacher),
            joinedload(ScheduleBlock.course_subject).joinedload(CourseSubject.course),
        ).order_by(ScheduleBlock.weekday, ScheduleBlock.start_time)
    ).all()


@schedule_router.post(
    "",
    response_model=ScheduleOut,
    status_code=201,
    dependencies=[Depends(require_management)],
)
def create_schedule(data: ScheduleIn, db: Session = Depends(get_db)):
    course_subject = _get_course_subject(db, data.course_subject_id)
    _validate_schedule(db, course_subject, data)
    schedule = ScheduleBlock(**data.model_dump())
    db.add(schedule)
    db.commit()
    return _get_schedule(db, schedule.id)


@schedule_router.put(
    "/{schedule_id}",
    response_model=ScheduleOut,
    dependencies=[Depends(require_management)],
)
def update_schedule(schedule_id: int, data: ScheduleIn, db: Session = Depends(get_db)):
    schedule = _get_schedule(db, schedule_id)
    course_subject = _get_course_subject(db, data.course_subject_id)
    _validate_schedule(db, course_subject, data, exclude_id=schedule.id)
    for key, value in data.model_dump().items():
        setattr(schedule, key, value)
    db.commit()
    db.expire_all()  # recarga la asignatura/curso del bloque
    return _get_schedule(db, schedule.id)


@schedule_router.delete(
    "/{schedule_id}", status_code=204, dependencies=[Depends(require_management)]
)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = _get_schedule(db, schedule_id)
    db.delete(schedule)
    db.commit()
