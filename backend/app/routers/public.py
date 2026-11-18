"""Portal público de postulación y verificación de certificados."""
import json
import secrets
from datetime import date as DateType

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Admission, AdmissionDocument, CertificateSignature, Course, Student
from ..schemas import (
    AdmissionDocumentOut,
    PublicAdmissionCreatedOut,
    PublicAdmissionIn,
    PublicAdmissionOut,
    PublicCourseOut,
)
from ..signing import verify
from .admissions import _check_course, _check_rut_free, _save_document

router = APIRouter(prefix="/public", tags=["Postulación en línea"])


def _tracking_url(token: str) -> str:
    return f"/postular/{token}"


def _documents(db: Session, admission_id: int) -> list[AdmissionDocument]:
    return list(
        db.scalars(
            select(AdmissionDocument)
            .where(AdmissionDocument.admission_id == admission_id)
            .order_by(AdmissionDocument.uploaded_at.desc(), AdmissionDocument.id.desc())
        ).all()
    )


def _serialize(admission: Admission, documents: list[AdmissionDocument]) -> dict:
    return {
        "token": admission.access_token,
        "status": admission.status,
        "applicant_name": admission.full_name,
        "course_name": admission.course.name if admission.course else None,
        "year": admission.year,
        "application_date": admission.application_date,
        "documents": [AdmissionDocumentOut.model_validate(d) for d in documents],
    }


def _by_token(db: Session, token: str) -> Admission:
    admission = db.scalar(
        select(Admission)
        .options(joinedload(Admission.course))
        .where(Admission.access_token == token)
    )
    if admission is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Postulación no encontrada"
        )
    return admission


@router.get("/courses", response_model=list[PublicCourseOut])
def public_courses(db: Session = Depends(get_db)):
    year = DateType.today().year
    courses = db.scalars(
        select(Course).where(Course.year == year).order_by(Course.name)
    ).all()
    counts = dict(
        db.execute(
            select(Student.course_id, func.count(Student.id))
            .where(Student.is_active.is_(True), Student.course_id.is_not(None))
            .group_by(Student.course_id)
        ).all()
    )
    return [
        {
            "id": course.id,
            "name": course.name,
            "level": course.level,
            "year": course.year,
            "capacity": course.capacity,
            "vacancies": max(course.capacity - counts.get(course.id, 0), 0),
        }
        for course in courses
    ]


@router.post(
    "/admissions", response_model=PublicAdmissionCreatedOut, status_code=201
)
def submit_admission(data: PublicAdmissionIn, db: Session = Depends(get_db)):
    _check_course(db, data.course_id)
    _check_rut_free(db, data.applicant_rut)
    course = db.get(Course, data.course_id) if data.course_id else None
    admission = Admission(
        **data.model_dump(exclude={"status", "year"}),
        status="postulada",
        year=course.year if course else DateType.today().year,
        access_token=secrets.token_urlsafe(24),
    )
    db.add(admission)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ya existe una postulación con ese RUT"
        )
    db.refresh(admission)
    result = _serialize(admission, [])
    result["tracking_url"] = _tracking_url(admission.access_token)
    return result


@router.get("/admissions/{token}", response_model=PublicAdmissionOut)
def track_admission(token: str, db: Session = Depends(get_db)):
    admission = _by_token(db, token)
    return _serialize(admission, _documents(db, admission.id))


@router.post(
    "/admissions/{token}/documents",
    response_model=AdmissionDocumentOut,
    status_code=201,
)
async def upload_public_document(
    token: str,
    name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    admission = _by_token(db, token)
    return await _save_document(db, admission, name, file)


@router.get("/certificates/{code}")
def verify_certificate(code: str, db: Session = Depends(get_db)):
    """Verificación pública de un certificado firmado electrónicamente."""
    record = db.scalar(
        select(CertificateSignature).where(
            CertificateSignature.code == code.strip().upper()
        )
    )
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Certificado no encontrado")
    payload = json.loads(record.payload)
    return {
        "valid": verify(payload, record.signature),
        "code": record.code,
        "certificate_number": record.certificate_number,
        "issued_on": record.issued_on,
        "student_name": payload.get("student_name"),
        "student_rut": payload.get("student_rut"),
        "course_name": payload.get("course_name"),
        "year": payload.get("year"),
        "algorithm": "HMAC-SHA256",
        "signed_on": record.created_at,
    }
