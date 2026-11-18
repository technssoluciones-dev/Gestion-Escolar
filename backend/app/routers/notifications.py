"""Avisos a las familias: generación automática y seguimiento de envío."""
from calendar import monthrange
from collections import defaultdict
from datetime import date as DateType
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..database import get_db
from ..mailer import EmailNotConfigured, send_email
from ..models import Attendance, Fee, Grade, Notification, Student
from ..schemas import (
    NotificationGenerateIn,
    NotificationGenerateOut,
    NotificationIn,
    NotificationOut,
    NotificationSummaryOut,
    NotificationUpdate,
    Page,
)
from ..security import require_management
from ..whatsapp import WhatsAppNotConfigured, normalize_phone, send_whatsapp

router = APIRouter(
    prefix="/notifications", tags=["Notificaciones"], dependencies=[Depends(require_management)]
)

STATUSES = ("pendiente", "enviada")
TYPES = ("inasistencia", "notas", "deuda", "general")
MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _current_period() -> str:
    today = DateType.today()
    return f"{today.year}-{today.month:02d}"


def _period_bounds(period: str) -> tuple[DateType, DateType]:
    year, month = int(period[:4]), int(period[5:])
    return DateType(year, month, 1), DateType(year, month, monthrange(year, month)[1])


def _period_label(period: str) -> str:
    year, month = int(period[:4]), int(period[5:])
    return f"{MONTHS[month - 1]} {year}"


def _money(amount: int) -> str:
    return f"${amount:,.0f}".replace(",", ".")


def _options():
    return (
        joinedload(Notification.student).joinedload(Student.course),
        joinedload(Notification.guardian),
    )


def _get_or_404(db: Session, notification_id: int) -> Notification:
    notification = db.scalar(
        select(Notification).options(*_options()).where(Notification.id == notification_id)
    )
    if notification is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aviso no encontrado")
    return notification


def _weighted_average(grades: list[Grade]) -> float | None:
    total_weight = sum(g.weight for g in grades)
    if not total_weight:
        return None
    return round(sum(float(g.score) * g.weight for g in grades) / total_weight, 1)


@router.get("", response_model=Page[NotificationOut])
def list_notifications(
    status_: str | None = Query(None, alias="status"),
    type_: str | None = Query(None, alias="type"),
    course_id: int | None = None,
    q: str | None = None,
    skip: int = 0,
    limit: int = Query(100, le=200),
    db: Session = Depends(get_db),
):
    if status_ and status_ not in STATUSES:
        raise HTTPException(422, "Estado de aviso no válido")
    if type_ and type_ not in TYPES:
        raise HTTPException(422, "Tipo de aviso no válido")
    query = select(Notification).join(Student, Student.id == Notification.student_id)
    if status_:
        query = query.where(Notification.status == status_)
    if type_:
        query = query.where(Notification.type == type_)
    if course_id is not None:
        query = query.where(Student.course_id == course_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                Student.first_name.ilike(like),
                Student.last_name.ilike(like),
                Student.rut.ilike(like),
                Notification.title.ilike(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(*_options())
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return {"items": items, "total": total}


@router.get("/summary", response_model=NotificationSummaryOut)
def notification_summary(db: Session = Depends(get_db)):
    summary = NotificationSummaryOut()
    for notification_status, count in db.execute(
        select(Notification.status, func.count()).group_by(Notification.status)
    ).all():
        if notification_status == "enviada":
            summary.sent = count
        else:
            summary.pending = count
    for notification_type, count in db.execute(
        select(Notification.type, func.count()).group_by(Notification.type)
    ).all():
        summary.by_type[notification_type] = count
    return summary


@router.post("/generate", response_model=NotificationGenerateOut)
def generate_notifications(data: NotificationGenerateIn, db: Session = Depends(get_db)):
    """Crea avisos para los estudiantes con inasistencia, promedio bajo o deuda vencida."""
    period = data.period or _current_period()
    first, last = _period_bounds(period)
    today = DateType.today()

    students = list(
        db.scalars(
            select(Student)
            .options(joinedload(Student.course))
            .where(Student.is_active.is_(True), Student.guardian_id.is_not(None))
        ).all()
    )
    if not students:
        return {"created": 0, "skipped": 0, "by_type": {}}
    student_ids = [student.id for student in students]
    by_id = {student.id: student for student in students}

    existing = set(
        db.scalars(
            select(Notification.dedupe_key).where(
                Notification.dedupe_key.in_(
                    [
                        f"{student_id}:{notification_type}:{period}"
                        for student_id in student_ids
                        for notification_type in data.types
                    ]
                )
            )
        ).all()
    )

    candidates: list[tuple[int, str, str, str]] = []  # (student_id, tipo, título, mensaje)

    if "inasistencia" in data.types:
        counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for record in db.scalars(
            select(Attendance).where(
                Attendance.student_id.in_(student_ids),
                Attendance.date >= first,
                Attendance.date <= last,
            )
        ).all():
            counts[record.student_id][record.status] += 1
        for student_id, student_counts in counts.items():
            total = sum(student_counts.values())
            if total < 5:
                continue
            present = student_counts.get("presente", 0) + student_counts.get("atrasado", 0)
            rate = round(present / total * 100, 1)
            if rate >= 85.0:
                continue
            student = by_id[student_id]
            candidates.append(
                (
                    student_id,
                    "inasistencia",
                    "Asistencia bajo lo esperado",
                    f"{student.full_name} registra {rate}% de asistencia en "
                    f"{_period_label(period)} ({total} días con registro). "
                    "Te invitamos a comunicarte con el colegio.",
                )
            )

    if "notas" in data.types:
        grades = list(
            db.scalars(select(Grade).where(Grade.student_id.in_(student_ids))).all()
        )
        by_student_subject: dict[int, dict[int, list[Grade]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for grade in grades:
            student = by_id[grade.student_id]
            if student.course_id is not None and grade.course_id != student.course_id:
                continue
            by_student_subject[grade.student_id][grade.subject_id].append(grade)
        for student_id, subjects in by_student_subject.items():
            averages = [_weighted_average(subject_grades) for subject_grades in subjects.values()]
            valid = [average for average in averages if average is not None]
            if not valid:
                continue
            overall = round(sum(valid) / len(valid), 1)
            if overall >= 4.0:
                continue
            student = by_id[student_id]
            course_name = student.course.name if student.course else "su curso"
            candidates.append(
                (
                    student_id,
                    "notas",
                    "Promedio general bajo 4.0",
                    f"El promedio general de {student.full_name} es {overall:.1f} en "
                    f"{course_name}. Se sugiere coordinar un acompañamiento académico.",
                )
            )

    if "deuda" in data.types:
        fees = list(
            db.scalars(
                select(Fee)
                .options(selectinload(Fee.payments))
                .where(Fee.student_id.in_(student_ids), Fee.due_date < today)
            ).all()
        )
        debts: dict[int, list[Fee]] = defaultdict(list)
        for fee in fees:
            if fee.balance > 0:
                debts[fee.student_id].append(fee)
        for student_id, student_fees in debts.items():
            student = by_id[student_id]
            total = sum(fee.balance for fee in student_fees)
            candidates.append(
                (
                    student_id,
                    "deuda",
                    "Cobros vencidos",
                    f"{student.full_name} mantiene {len(student_fees)} cobro(s) vencido(s) "
                    f"por un total de {_money(total)}. Por favor regulariza el pago o "
                    "comunícate con secretaría.",
                )
            )

    created = 0
    skipped = 0
    by_type: dict[str, int] = defaultdict(int)
    for student_id, notification_type, title, message in candidates:
        key = f"{student_id}:{notification_type}:{period}"
        if key in existing:
            skipped += 1
            continue
        student = by_id[student_id]
        db.add(
            Notification(
                student_id=student_id,
                guardian_id=student.guardian_id,
                type=notification_type,
                period=period,
                title=title,
                message=message,
                dedupe_key=key,
            )
        )
        existing.add(key)
        created += 1
        by_type[notification_type] += 1
    db.commit()
    return {"created": created, "skipped": skipped, "by_type": dict(by_type)}


@router.post("", response_model=NotificationOut, status_code=201)
def create_notification(data: NotificationIn, db: Session = Depends(get_db)):
    student = db.get(Student, data.student_id)
    if student is None or not student.is_active:
        raise HTTPException(422, "El estudiante indicado no existe o no está activo")
    notification = Notification(
        student_id=student.id,
        guardian_id=student.guardian_id,
        type=data.type,
        period=data.period or _current_period(),
        title=data.title,
        message=data.message,
    )
    db.add(notification)
    db.commit()
    return _get_or_404(db, notification.id)


@router.put("/{notification_id}", response_model=NotificationOut)
def update_notification(
    notification_id: int, data: NotificationUpdate, db: Session = Depends(get_db)
):
    notification = _get_or_404(db, notification_id)
    notification.status = data.status
    notification.sent_at = datetime.now() if data.status == "enviada" else None
    db.commit()
    db.expire_all()
    return _get_or_404(db, notification.id)


@router.post("/{notification_id}/email", response_model=NotificationOut)
def send_notification_email(
    notification_id: int, db: Session = Depends(get_db)
):
    notification = _get_or_404(db, notification_id)
    if notification.status == "enviada":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Este aviso ya fue enviado"
        )
    guardian = notification.guardian
    if guardian is None or not guardian.email:
        raise HTTPException(
            422, "El apoderado del estudiante no tiene correo registrado"
        )
    body = (
        f"Hola {guardian.first_name},\n\n"
        f"{notification.message}\n\n"
        "Este aviso fue enviado por el colegio. También puedes revisarlo en el "
        "portal de familias.\n\nGestión Escolar"
    )
    try:
        send_email(guardian.email, notification.title, body)
    except EmailNotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except Exception:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "No se pudo enviar el correo. Revisa la configuración SMTP.",
        )
    notification.status = "enviada"
    notification.channel = "email"
    notification.sent_at = datetime.now()
    db.commit()
    db.expire_all()
    return _get_or_404(db, notification.id)


@router.post("/{notification_id}/whatsapp", response_model=NotificationOut)
def send_notification_whatsapp(
    notification_id: int, db: Session = Depends(get_db)
):
    notification = _get_or_404(db, notification_id)
    if notification.status == "enviada":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Este aviso ya fue enviado"
        )
    guardian = notification.guardian
    if guardian is None or not guardian.phone:
        raise HTTPException(
            422, "El apoderado del estudiante no tiene teléfono registrado"
        )
    try:
        phone = normalize_phone(guardian.phone)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    body = f"{notification.title}\n\n{notification.message}\n\n— Gestión Escolar"
    try:
        send_whatsapp(phone, body)
    except WhatsAppNotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except Exception:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "No se pudo enviar el WhatsApp. Revisa la configuración del proveedor.",
        )
    notification.status = "enviada"
    notification.channel = "whatsapp"
    notification.sent_at = datetime.now()
    db.commit()
    db.expire_all()
    return _get_or_404(db, notification.id)


@router.delete("/{notification_id}", status_code=204)
def delete_notification(notification_id: int, db: Session = Depends(get_db)):
    notification = _get_or_404(db, notification_id)
    db.delete(notification)
    db.commit()
