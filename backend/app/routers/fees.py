from datetime import date as DateType

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..database import get_db
from ..models import Course, Fee, Payment, Student
from ..rut import normalize_rut
from ..schemas import (
    FeeGenerateIn,
    FeeGenerateOut,
    FeeIn,
    FeeOut,
    FeeSummaryOut,
    Page,
    PaymentIn,
    PaymentOut,
)
from ..security import require_management

router = APIRouter(
    prefix="/fees", tags=["Pagos"], dependencies=[Depends(require_management)]
)

STATUSES = ("pendiente", "parcial", "pagada", "vencida")


def _fee_options():
    return (
        joinedload(Fee.student).joinedload(Student.course),
        selectinload(Fee.payments),
    )


def _get_or_404(db: Session, fee_id: int) -> Fee:
    fee = db.scalar(
        select(Fee).options(*_fee_options()).where(Fee.id == fee_id)
    )
    if fee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cobro no encontrado")
    return fee


def _query(
    q: str | None,
    student_id: int | None,
    course_id: int | None,
    concept: str | None,
    period: str | None,
):
    query = select(Fee).join(Student, Student.id == Fee.student_id)
    if q:
        like = f"%{q.strip()}%"
        conditions = [
            Student.first_name.ilike(like),
            Student.last_name.ilike(like),
        ]
        try:
            conditions.append(Student.rut == normalize_rut(q))
        except ValueError:
            pass
        query = query.where(or_(*conditions))
    if student_id is not None:
        query = query.where(Fee.student_id == student_id)
    if course_id is not None:
        query = query.where(Student.course_id == course_id)
    if concept:
        query = query.where(Fee.concept == concept)
    if period:
        query = query.where(Fee.period == period)
    return query


def _filtered(
    db: Session,
    q: str | None,
    student_id: int | None,
    course_id: int | None,
    concept: str | None,
    period: str | None,
    fee_status: str | None,
) -> list[Fee]:
    if fee_status and fee_status not in STATUSES:
        raise HTTPException(422, "Estado de cobro no válido")
    query = _query(q, student_id, course_id, concept, period)
    fees = list(
        db.scalars(
            query.options(*_fee_options()).order_by(
                Fee.due_date.desc(), Fee.id.desc()
            )
        ).all()
    )
    if fee_status:
        fees = [fee for fee in fees if fee.status == fee_status]
    return fees


@router.get("", response_model=Page[FeeOut])
def list_fees(
    q: str | None = None,
    student_id: int | None = None,
    course_id: int | None = None,
    concept: str | None = None,
    period: str | None = None,
    status_: str | None = Query(None, alias="status"),
    skip: int = 0,
    limit: int = Query(100, le=200),
    db: Session = Depends(get_db),
):
    if concept and concept not in ("matricula", "mensualidad", "cuota", "otro"):
        raise HTTPException(422, "Tipo de cobro no válido")
    fees = _filtered(db, q, student_id, course_id, concept, period, status_)
    return {"items": fees[skip : skip + limit], "total": len(fees)}


@router.get("/summary", response_model=FeeSummaryOut)
def fee_summary(
    q: str | None = None,
    student_id: int | None = None,
    course_id: int | None = None,
    concept: str | None = None,
    period: str | None = None,
    status_: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    fees = _filtered(db, q, student_id, course_id, concept, period, status_)
    summary = FeeSummaryOut()
    for fee in fees:
        summary.charged += fee.amount
        summary.collected += fee.paid_amount
        if fee.status == "vencida":
            summary.overdue += fee.balance
            summary.overdue_count += 1
        elif fee.status != "pagada":
            summary.pending += fee.balance
            summary.pending_count += 1
        else:
            summary.paid_count += 1
    return summary


@router.post("", response_model=FeeOut, status_code=201)
def create_fee(data: FeeIn, db: Session = Depends(get_db)):
    if db.get(Student, data.student_id) is None:
        raise HTTPException(422, "El estudiante indicado no existe")
    fee = Fee(**data.model_dump())
    db.add(fee)
    db.commit()
    db.expire_all()
    return _get_or_404(db, fee.id)


@router.post("/generate", response_model=FeeGenerateOut)
def generate_fees(data: FeeGenerateIn, db: Session = Depends(get_db)):
    course = db.get(Course, data.course_id)
    if course is None:
        raise HTTPException(422, "El curso indicado no existe")
    students = db.scalars(
        select(Student).where(
            Student.course_id == course.id, Student.is_active.is_(True)
        )
    ).all()
    existing = {
        fee.student_id
        for fee in db.scalars(
            select(Fee).where(
                Fee.concept == data.concept, Fee.period == data.period
            )
        ).all()
    }
    created = 0
    skipped = 0
    for student in students:
        if student.id in existing:
            skipped += 1
            continue
        db.add(
            Fee(
                student_id=student.id,
                concept=data.concept,
                description=data.description,
                period=data.period,
                amount=data.amount,
                due_date=data.due_date,
            )
        )
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped}


@router.get("/{fee_id}", response_model=FeeOut)
def get_fee(fee_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, fee_id)


@router.put("/{fee_id}", response_model=FeeOut)
def update_fee(fee_id: int, data: FeeIn, db: Session = Depends(get_db)):
    fee = _get_or_404(db, fee_id)
    if fee.payments:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No se puede editar un cobro que ya tiene pagos registrados",
        )
    if db.get(Student, data.student_id) is None:
        raise HTTPException(422, "El estudiante indicado no existe")
    for key, value in data.model_dump().items():
        setattr(fee, key, value)
    db.commit()
    db.expire_all()
    return _get_or_404(db, fee.id)


@router.delete("/{fee_id}", status_code=204)
def delete_fee(fee_id: int, db: Session = Depends(get_db)):
    fee = _get_or_404(db, fee_id)
    if fee.payments:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No se puede eliminar un cobro que ya tiene pagos registrados",
        )
    db.delete(fee)
    db.commit()


@router.post("/{fee_id}/payments", response_model=PaymentOut, status_code=201)
def register_payment(
    fee_id: int, data: PaymentIn, db: Session = Depends(get_db)
):
    fee = _get_or_404(db, fee_id)
    if fee.balance <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este cobro ya está pagado")
    if data.amount > fee.balance:
        raise HTTPException(
            422, f"El monto supera el saldo pendiente ({fee.balance} pesos)"
        )
    payment = Payment(fee_id=fee.id, **data.model_dump())
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


@router.delete("/{fee_id}/payments/{payment_id}", status_code=204)
def delete_payment(
    fee_id: int, payment_id: int, db: Session = Depends(get_db)
):
    payment = db.get(Payment, payment_id)
    if payment is None or payment.fee_id != fee_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pago no encontrado")
    db.delete(payment)
    db.commit()
