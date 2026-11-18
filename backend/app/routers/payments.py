"""Pagos en línea: checkout, confirmación, Webpay y conciliación bancaria.

Con WEBPAY_COMMERCE_CODE/WEBPAY_API_KEY configurados el checkout se crea en
Webpay Plus y la confirmación ocurre en el retorno del gateway. Sin ellas se
usa una simulación local ("sandbox") que imita el mismo flujo.
"""
import csv
import io
import re
import secrets
from datetime import date as DateType
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from .. import webpay
from ..config import settings
from ..database import get_db
from ..models import BankMovement, Fee, Payment, PaymentIntent, Student, User
from ..schemas import (
    BankImportOut,
    BankMatchIn,
    BankMovementOut,
    Page,
    PaymentCheckoutIn,
    PaymentCheckoutOut,
    PaymentIntentOut,
)
from ..security import require_management, require_portal

router = APIRouter(prefix="/payments", tags=["Pagos en línea"])

STATUSES = ("pendiente", "pagada", "cancelada")


def _options():
    return joinedload(PaymentIntent.fee).joinedload(Fee.student).joinedload(
        Student.course
    )


def _get_intent(db: Session, token: str) -> PaymentIntent:
    intent = db.scalar(
        select(PaymentIntent)
        .options(_options())
        .where(PaymentIntent.token == token)
    )
    if intent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pago no encontrado")
    return intent


def _authorize_student(user: User, student: Student) -> None:
    if user.role == "estudiante" and user.student_id == student.id:
        return
    if user.role == "apoderado" and user.guardian_id == student.guardian_id:
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN, "No puedes pagar los cobros de este estudiante"
    )


def _authorize(db: Session, user: User, intent: PaymentIntent) -> None:
    student = db.get(Student, intent.fee.student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estudiante no encontrado")
    _authorize_student(user, student)


def _checkout_url(token: str) -> str:
    return f"/portal/pagar/{token}"


def _settle(db: Session, intent: PaymentIntent, reference: str, note: str) -> Payment:
    fee = intent.fee
    amount = min(intent.amount, fee.balance)
    if amount <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este cobro ya está pagado")
    payment = Payment(
        fee_id=fee.id,
        amount=amount,
        paid_on=DateType.today(),
        method="tarjeta",
        reference=reference,
        note=note,
    )
    db.add(payment)
    db.flush()
    intent.amount = amount
    intent.payment_id = payment.id
    intent.status = "pagada"
    intent.paid_at = datetime.now()
    db.commit()
    db.expire_all()
    return payment


def _webpay_checkout(intent: PaymentIntent, fee: Fee) -> PaymentCheckoutOut:
    if intent.amount != fee.balance:
        intent.amount = fee.balance
        intent.gateway_token = None
        intent.gateway_url = None
    if not intent.gateway_token or not intent.gateway_url:
        try:
            transaction = webpay.create_transaction(
                buy_order=f"INT{intent.id:08d}",
                session_id=intent.token[:32],
                amount=intent.amount,
                return_url=f"{settings.public_api_url}/payments/webpay/return",
            )
        except webpay.WebpayNotConfigured as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
        except webpay.WebpayError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
        token = transaction.get("token")
        url = transaction.get("url")
        if not token or not url:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Webpay no devolvió el token de pago"
            )
        intent.provider = "webpay"
        intent.gateway_token = str(token)
        intent.gateway_url = str(url)
    return {
        "intent": intent,
        "checkout_url": _checkout_url(intent.token),
        "provider": "webpay",
        "webpay_url": intent.gateway_url,
        "webpay_token": intent.gateway_token,
    }


@router.post("/checkout", response_model=PaymentCheckoutOut)
def create_checkout(
    data: PaymentCheckoutIn,
    user: User = Depends(require_portal),
    db: Session = Depends(get_db),
):
    fee = db.scalar(
        select(Fee)
        .options(joinedload(Fee.student).joinedload(Student.course))
        .where(Fee.id == data.fee_id)
    )
    if fee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cobro no encontrado")
    _authorize_student(user, fee.student)
    if fee.balance <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este cobro ya está pagado")

    intent = db.scalar(
        select(PaymentIntent)
        .options(_options())
        .where(
            PaymentIntent.fee_id == fee.id,
            PaymentIntent.status == "pendiente",
        )
        .order_by(PaymentIntent.id.desc())
    )
    if intent is None:
        intent = PaymentIntent(
            token=secrets.token_urlsafe(24),
            fee_id=fee.id,
            amount=fee.balance,
            provider="webpay" if webpay.is_configured() else "sandbox",
        )
        db.add(intent)
        db.commit()
        intent = _get_intent(db, intent.token)

    if webpay.is_configured():
        result = _webpay_checkout(intent, fee)
        db.commit()
        intent = _get_intent(db, intent.token)
        result["intent"] = intent
        if intent.status == "pendiente":
            result["webpay_url"] = intent.gateway_url
            result["webpay_token"] = intent.gateway_token
        return result

    if intent.provider == "webpay":
        # El gateway real ya no está configurado: se reinicia el intento.
        intent.provider = "sandbox"
        intent.gateway_token = None
        intent.gateway_url = None
    if intent.amount != fee.balance:
        intent.amount = fee.balance
    db.commit()
    intent = _get_intent(db, intent.token)
    return {"intent": intent, "checkout_url": _checkout_url(intent.token)}


@router.get("/intents", response_model=Page[PaymentIntentOut])
def list_intents(
    status_: str | None = Query(None, alias="status"),
    q: str | None = None,
    skip: int = 0,
    limit: int = Query(100, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_management),
):
    if status_ and status_ not in STATUSES:
        raise HTTPException(422, "Estado de pago no válido")
    query = (
        select(PaymentIntent)
        .join(Fee, Fee.id == PaymentIntent.fee_id)
        .join(Student, Student.id == Fee.student_id)
    )
    if status_:
        query = query.where(PaymentIntent.status == status_)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                Student.first_name.ilike(like),
                Student.last_name.ilike(like),
                Student.rut.ilike(like),
                PaymentIntent.token.ilike(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(_options())
        .order_by(PaymentIntent.created_at.desc(), PaymentIntent.id.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return {"items": items, "total": total}


@router.get("/intents/{token}", response_model=PaymentIntentOut)
def get_intent(
    token: str,
    user: User = Depends(require_portal),
    db: Session = Depends(get_db),
):
    intent = _get_intent(db, token)
    _authorize(db, user, intent)
    return intent


@router.post("/intents/{token}/confirm", response_model=PaymentIntentOut)
def confirm_payment(
    token: str,
    user: User = Depends(require_portal),
    db: Session = Depends(get_db),
):
    intent = _get_intent(db, token)
    _authorize(db, user, intent)
    if intent.status == "pagada":
        return intent
    if intent.status == "cancelada":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Este pago fue cancelado; inicia uno nuevo"
        )
    if intent.provider == "webpay":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El pago debe confirmarse en Webpay"
        )
    fee = intent.fee
    if fee.balance <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este cobro ya está pagado")

    _settle(
        db,
        intent,
        reference=f"ONLINE-{token[:10].upper()}",
        note="Pago en línea (pasarela simulada)",
    )
    return _get_intent(db, token)


@router.post("/intents/{token}/cancel", response_model=PaymentIntentOut)
def cancel_payment(
    token: str,
    user: User = Depends(require_portal),
    db: Session = Depends(get_db),
):
    intent = _get_intent(db, token)
    _authorize(db, user, intent)
    if intent.status == "pagada":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El pago ya fue confirmado y no se puede cancelar"
        )
    if intent.status == "pendiente":
        intent.status = "cancelada"
        db.commit()
        db.expire_all()
    return _get_intent(db, token)


def _gateway_intent(db: Session, gateway_token: str | None) -> PaymentIntent | None:
    if not gateway_token:
        return None
    return db.scalar(
        select(PaymentIntent)
        .options(_options())
        .where(PaymentIntent.gateway_token == gateway_token)
    )


def _frontend_return(intent: PaymentIntent | None, result: str) -> RedirectResponse:
    if intent is None:
        return RedirectResponse(f"{settings.frontend_url}/portal", status_code=303)
    return RedirectResponse(
        f"{settings.frontend_url}/portal/pagar/{intent.token}?webpay={result}",
        status_code=303,
    )


@router.post("/webpay/return", include_in_schema=False)
def webpay_return(
    token_ws: str | None = Form(None),
    TBK_TOKEN: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Retorno del navegador desde Webpay: confirma el cobro y vuelve al portal."""
    intent = _gateway_intent(db, token_ws or TBK_TOKEN)
    if intent is None:
        return _frontend_return(None, "error")
    if token_ws is None:
        if intent.status == "pendiente":
            intent.status = "cancelada"
            db.commit()
        return _frontend_return(intent, "cancelado")
    if intent.status == "pagada":
        return _frontend_return(intent, "ok")
    if intent.status == "cancelada":
        return _frontend_return(intent, "cancelado")
    try:
        response = webpay.commit_transaction(token_ws)
    except webpay.WebpayError:
        intent.status = "cancelada"
        db.commit()
        return _frontend_return(intent, "error")
    if response.get("status") != "AUTHORIZED" or int(response.get("response_code", -1)) != 0:
        intent.status = "cancelada"
        db.commit()
        return _frontend_return(intent, "rechazado")
    if int(response.get("amount", 0)) != intent.amount:
        intent.status = "cancelada"
        db.commit()
        return _frontend_return(intent, "error")
    _settle(
        db,
        intent,
        reference=f"WEBPAY-{(response.get('buy_order') or intent.gateway_token or '')[:20]}",
        note="Pago en línea (Webpay Plus)",
    )
    return _frontend_return(intent, "ok")


def _parse_amount(raw: str) -> int:
    text = re.sub(r"[^\d,.\-]", "", raw or "")
    if not text:
        raise ValueError("monto vacío")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        if re.search(r",\d{1,2}$", text):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "." in text and not re.search(r"\.\d{1,2}$", text):
        text = text.replace(".", "")
    return int(round(float(text)))


def _parse_date(raw: str) -> DateType:
    text = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"fecha no reconocida: {raw}")


def _auto_match(db: Session, movement: BankMovement) -> None:
    if movement.reference:
        payment = db.scalar(
            select(Payment).where(Payment.reference == movement.reference.strip())
        )
        if payment is not None:
            movement.status = "conciliado"
            movement.payment_id = payment.id
            movement.fee_id = payment.fee_id
            return
    digits = re.sub(r"[^0-9k]", "", (movement.description or "").lower())
    if len(digits) < 7:
        return
    for student in db.scalars(select(Student).where(Student.is_active.is_(True))).all():
        rut_digits = re.sub(r"[^0-9k]", "", student.rut.lower())
        if rut_digits not in digits:
            continue
        fee = None
        for candidate in db.scalars(
            select(Fee)
            .where(Fee.student_id == student.id)
            .order_by(Fee.due_date.asc(), Fee.id.asc())
        ).all():
            if candidate.balance == movement.amount:
                fee = candidate
                break
        if fee is None:
            continue
        payment = Payment(
            fee_id=fee.id,
            amount=min(movement.amount, fee.balance),
            paid_on=movement.movement_date,
            method="transferencia",
            reference=f"CARTOLA-{movement.id:05d}",
            note="Conciliación bancaria automática",
        )
        db.add(payment)
        db.flush()
        movement.status = "conciliado"
        movement.fee_id = fee.id
        movement.payment_id = payment.id
        return


def _bank_options():
    return joinedload(BankMovement.fee).joinedload(Fee.student)


@router.get("/bank", response_model=Page[BankMovementOut])
def list_bank_movements(
    status_: str | None = Query(None, alias="status"),
    skip: int = 0,
    limit: int = Query(100, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_management),
):
    if status_ and status_ not in ("pendiente", "conciliado"):
        raise HTTPException(422, "Estado de conciliación no válido")
    query = select(BankMovement)
    if status_:
        query = query.where(BankMovement.status == status_)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(_bank_options())
        .order_by(BankMovement.movement_date.desc(), BankMovement.id.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return {"items": items, "total": total}


@router.post("/bank/import", response_model=BankImportOut)
async def import_bank_movements(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_management),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(422, "El archivo está vacío")
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(422, "El archivo supera 2 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    sample = text.splitlines()[0] if text.splitlines() else ""
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    names = {(name or "").strip().lower(): name for name in (reader.fieldnames or [])}

    def column(*candidates: str) -> str | None:
        for candidate in candidates:
            if candidate in names:
                return names[candidate]
        return None

    date_col = column("fecha", "date", "fecha movimiento", "fecha operacion")
    desc_col = column("descripcion", "descripción", "detalle", "glosa", "description")
    amount_col = column("monto", "abono", "amount", "credito", "crédito")
    ref_col = column("referencia", "reference", "documento", "nro documento")
    if not date_col or not desc_col or not amount_col:
        raise HTTPException(
            422, "El CSV debe tener columnas fecha, descripcion y monto (abono)"
        )

    imported = matched = skipped = 0
    for row in reader:
        try:
            movement_date = _parse_date(row.get(date_col, ""))
            amount = _parse_amount(row.get(amount_col, ""))
        except (ValueError, TypeError):
            skipped += 1
            continue
        if amount <= 0:
            skipped += 1
            continue
        description = (row.get(desc_col) or "").strip()[:200]
        reference = (row.get(ref_col) or "").strip()[:80] if ref_col else ""
        reference = reference or None
        if not description:
            skipped += 1
            continue
        exists = db.scalar(
            select(BankMovement).where(
                BankMovement.movement_date == movement_date,
                BankMovement.amount == amount,
                BankMovement.description == description,
                BankMovement.reference == reference,
            )
        )
        if exists is not None:
            skipped += 1
            continue
        movement = BankMovement(
            movement_date=movement_date,
            description=description,
            reference=reference,
            amount=amount,
        )
        db.add(movement)
        db.flush()
        _auto_match(db, movement)
        imported += 1
        if movement.status == "conciliado":
            matched += 1
    db.commit()
    return {
        "imported": imported,
        "matched": matched,
        "pending": imported - matched,
        "skipped": skipped,
    }


@router.post("/bank/{movement_id}/match", response_model=BankMovementOut)
def match_bank_movement(
    movement_id: int,
    data: BankMatchIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_management),
):
    movement = db.scalar(
        select(BankMovement).options(_bank_options()).where(BankMovement.id == movement_id)
    )
    if movement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Movimiento no encontrado")
    if movement.status == "conciliado":
        raise HTTPException(status.HTTP_409_CONFLICT, "El movimiento ya está conciliado")
    fee = db.scalar(
        select(Fee)
        .options(joinedload(Fee.student))
        .where(Fee.id == data.fee_id)
    )
    if fee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cobro no encontrado")
    if fee.balance <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "El cobro ya está pagado")
    payment = Payment(
        fee_id=fee.id,
        amount=min(movement.amount, fee.balance),
        paid_on=movement.movement_date,
        method="transferencia",
        reference=f"CARTOLA-{movement.id:05d}",
        note="Conciliación bancaria manual",
    )
    db.add(payment)
    db.flush()
    movement.status = "conciliado"
    movement.fee_id = fee.id
    movement.payment_id = payment.id
    db.commit()
    db.expire_all()
    return db.scalar(
        select(BankMovement).options(_bank_options()).where(BankMovement.id == movement_id)
    )
