from datetime import date as DateType
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import (
    Admission,
    AdmissionDocument,
    AdmissionInterview,
    AdmissionScore,
    Course,
    Guardian,
    Student,
)
from ..rut import normalize_rut
from ..schemas import (
    AdmissionDocumentOut,
    AdmissionDossierOut,
    AdmissionEnrollIn,
    AdmissionIn,
    AdmissionInterviewIn,
    AdmissionInterviewOut,
    AdmissionOut,
    AdmissionScoreIn,
    AdmissionScoreOut,
    Page,
)
from ..security import require_management

router = APIRouter(prefix="/admissions", tags=["Admisiones"], dependencies=[Depends(require_management)])
documents_router = APIRouter(
    prefix="/admission-documents",
    tags=["Admisiones"],
    dependencies=[Depends(require_management)],
)
interviews_router = APIRouter(
    prefix="/admission-interviews",
    tags=["Admisiones"],
    dependencies=[Depends(require_management)],
)
scores_router = APIRouter(
    prefix="/admission-scores",
    tags=["Admisiones"],
    dependencies=[Depends(require_management)],
)

STATUSES = ("postulada", "en_revision", "aceptada", "rechazada", "matriculada")
PENDING_STATUSES = ("postulada", "en_revision")
MAX_DOCUMENT_SIZE = 5 * 1024 * 1024
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


def _get_or_404(db: Session, admission_id: int) -> Admission:
    admission = db.scalar(
        select(Admission)
        .options(joinedload(Admission.course), joinedload(Admission.student))
        .where(Admission.id == admission_id)
    )
    if admission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Postulación no encontrada")
    return admission


def _check_course(db: Session, course_id: int | None) -> None:
    if course_id is not None and db.get(Course, course_id) is None:
        raise HTTPException(422, "El curso indicado no existe")


def _check_rut_free(db: Session, rut: str, exclude_id: int | None = None) -> None:
    found = db.scalar(select(Admission).where(Admission.applicant_rut == rut))
    if found and found.id != exclude_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ya existe una postulación con ese RUT"
        )
    student = db.scalar(select(Student).where(Student.rut == rut))
    if student is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ya existe un estudiante con ese RUT"
        )


def _reject_direct_enrollment() -> None:
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        "Para matricular usa la acción 'Matricular', que crea la ficha del estudiante",
    )


@router.get("", response_model=Page[AdmissionOut])
def list_admissions(
    q: str | None = None,
    status_: str | None = Query(None, alias="status"),
    year: int | None = None,
    course_id: int | None = None,
    skip: int = 0,
    limit: int = Query(100, le=200),
    db: Session = Depends(get_db),
):
    query = select(Admission)
    if q:
        like = f"%{q.strip()}%"
        conditions = [
            Admission.first_name.ilike(like),
            Admission.last_name.ilike(like),
            Admission.guardian_first_name.ilike(like),
            Admission.guardian_last_name.ilike(like),
        ]
        try:
            conditions.append(Admission.applicant_rut == normalize_rut(q))
        except ValueError:
            pass
        query = query.where(or_(*conditions))
    if status_:
        if status_ not in STATUSES:
            raise HTTPException(422, "Estado de postulación no válido")
        query = query.where(Admission.status == status_)
    if year is not None:
        query = query.where(Admission.year == year)
    if course_id is not None:
        query = query.where(Admission.course_id == course_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(joinedload(Admission.course), joinedload(Admission.student))
        .order_by(Admission.application_date.desc(), Admission.last_name, Admission.first_name)
        .offset(skip)
        .limit(limit)
    ).all()
    return {"items": items, "total": total}


@router.post("", response_model=AdmissionOut, status_code=201)
def create_admission(data: AdmissionIn, db: Session = Depends(get_db)):
    if data.status == "matriculada":
        _reject_direct_enrollment()
    _check_course(db, data.course_id)
    _check_rut_free(db, data.applicant_rut)
    admission = Admission(**data.model_dump())
    db.add(admission)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ya existe una postulación con ese RUT"
        )
    return _get_or_404(db, admission.id)


@router.get("/{admission_id}", response_model=AdmissionOut)
def get_admission(admission_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, admission_id)


@router.put("/{admission_id}", response_model=AdmissionOut)
def update_admission(admission_id: int, data: AdmissionIn, db: Session = Depends(get_db)):
    admission = _get_or_404(db, admission_id)
    if admission.status == "matriculada":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La postulación ya fue matriculada; edita la ficha del estudiante",
        )
    if data.status == "matriculada":
        _reject_direct_enrollment()
    _check_course(db, data.course_id)
    _check_rut_free(db, data.applicant_rut, exclude_id=admission.id)
    for key, value in data.model_dump().items():
        setattr(admission, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ya existe una postulación con ese RUT"
        )
    db.expire_all()
    return _get_or_404(db, admission.id)


@router.delete("/{admission_id}", status_code=204)
def delete_admission(admission_id: int, db: Session = Depends(get_db)):
    admission = _get_or_404(db, admission_id)
    if admission.status == "matriculada":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No se puede eliminar: la postulación ya fue matriculada",
        )
    db.delete(admission)
    db.commit()


@router.post("/{admission_id}/enroll", response_model=AdmissionOut)
def enroll_admission(
    admission_id: int, data: AdmissionEnrollIn, db: Session = Depends(get_db)
):
    admission = _get_or_404(db, admission_id)
    if admission.status == "matriculada" or admission.student_id is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Esta postulación ya fue matriculada"
        )

    course_id = data.course_id or admission.course_id
    if course_id is None:
        raise HTTPException(422, "Selecciona un curso para matricular")
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(422, "El curso indicado no existe")

    enrolled = db.scalar(
        select(func.count(Student.id)).where(
            Student.course_id == course.id, Student.is_active.is_(True)
        )
    ) or 0
    if enrolled >= course.capacity:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"El curso {course.name} no tiene cupos disponibles ({course.capacity})",
        )

    if db.scalar(select(Student).where(Student.rut == admission.applicant_rut)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ya existe un estudiante con ese RUT"
        )

    guardian: Guardian | None = None
    if admission.guardian_rut:
        guardian = db.scalar(
            select(Guardian).where(Guardian.rut == admission.guardian_rut)
        )
        if guardian is None:
            if not (admission.guardian_first_name and admission.guardian_last_name):
                raise HTTPException(
                    422,
                    "Falta el nombre y apellido del apoderado para crear su ficha",
                )
            guardian = Guardian(
                rut=admission.guardian_rut,
                first_name=admission.guardian_first_name,
                last_name=admission.guardian_last_name,
                email=admission.guardian_email,
                phone=admission.guardian_phone,
            )
            db.add(guardian)
            db.flush()

    student = Student(
        rut=admission.applicant_rut,
        first_name=admission.first_name,
        last_name=admission.last_name,
        birth_date=admission.birth_date,
        gender=admission.gender,
        email=admission.email,
        address=admission.address,
        enrollment_date=DateType.today(),
        status="activo",
        is_active=True,
        course_id=course.id,
        guardian_id=guardian.id if guardian else None,
    )
    db.add(student)
    try:
        db.flush()
        admission.student_id = student.id
        admission.status = "matriculada"
        admission.course_id = course.id
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ya existe un estudiante con ese RUT"
        )
    db.expire_all()
    return _get_or_404(db, admission.id)


# ---------- Expediente: documentos, entrevistas y puntajes ----------
def _weighted_score(scores: list[AdmissionScore]) -> float | None:
    total_weight = sum(score.weight for score in scores)
    if not total_weight:
        return None
    return round(
        sum(float(score.score) * score.weight for score in scores) / total_weight, 1
    )


def _document_or_404(db: Session, document_id: int) -> AdmissionDocument:
    document = db.get(AdmissionDocument, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")
    return document


def _interview_or_404(db: Session, interview_id: int) -> AdmissionInterview:
    interview = db.get(AdmissionInterview, interview_id)
    if interview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entrevista no encontrada")
    return interview


def _score_or_404(db: Session, score_id: int) -> AdmissionScore:
    score = db.get(AdmissionScore, score_id)
    if score is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Puntaje no encontrado")
    return score


@router.get("/{admission_id}/dossier", response_model=AdmissionDossierOut)
def get_dossier(admission_id: int, db: Session = Depends(get_db)):
    admission = _get_or_404(db, admission_id)
    documents = db.scalars(
        select(AdmissionDocument)
        .where(AdmissionDocument.admission_id == admission.id)
        .order_by(AdmissionDocument.uploaded_at.desc(), AdmissionDocument.id.desc())
    ).all()
    interviews = db.scalars(
        select(AdmissionInterview)
        .where(AdmissionInterview.admission_id == admission.id)
        .order_by(AdmissionInterview.scheduled_at, AdmissionInterview.id)
    ).all()
    scores = db.scalars(
        select(AdmissionScore)
        .where(AdmissionScore.admission_id == admission.id)
        .order_by(AdmissionScore.criterion)
    ).all()
    return {
        "documents": documents,
        "interviews": interviews,
        "scores": scores,
        "weighted_score": _weighted_score(list(scores)),
    }


async def _save_document(
    db: Session, admission: Admission, name: str, file: UploadFile
) -> AdmissionDocument:
    name = name.strip()
    if not name:
        raise HTTPException(422, "Indica un nombre para el documento")
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(422, "Solo se permiten archivos PDF, JPG o PNG")
    data = await file.read()
    if not data:
        raise HTTPException(422, "El archivo está vacío")
    if len(data) > MAX_DOCUMENT_SIZE:
        raise HTTPException(422, "El archivo supera el máximo de 5 MB")
    filename = (file.filename or "documento").replace("\\", "/").split("/")[-1]
    document = AdmissionDocument(
        admission_id=admission.id,
        name=name,
        filename=filename[:255],
        content_type=content_type,
        size=len(data),
        data=data,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@router.post(
    "/{admission_id}/documents", response_model=AdmissionDocumentOut, status_code=201
)
async def upload_document(
    admission_id: int,
    name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    admission = _get_or_404(db, admission_id)
    return await _save_document(db, admission, name, file)


@documents_router.get("/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db)):
    document = _document_or_404(db, document_id)
    safe_name = document.filename.encode("ascii", "ignore").decode().replace('"', "")
    return Response(
        content=document.data,
        media_type=document.content_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{safe_name or "documento"}"; '
                f"filename*=UTF-8''{quote(document.filename)}"
            )
        },
    )


@documents_router.delete("/{document_id}", status_code=204)
def delete_document(document_id: int, db: Session = Depends(get_db)):
    document = _document_or_404(db, document_id)
    db.delete(document)
    db.commit()


@router.get("/{admission_id}/interviews", response_model=list[AdmissionInterviewOut])
def list_interviews(admission_id: int, db: Session = Depends(get_db)):
    admission = _get_or_404(db, admission_id)
    return db.scalars(
        select(AdmissionInterview)
        .where(AdmissionInterview.admission_id == admission.id)
        .order_by(AdmissionInterview.scheduled_at, AdmissionInterview.id)
    ).all()


@router.post(
    "/{admission_id}/interviews", response_model=AdmissionInterviewOut, status_code=201
)
def create_interview(
    admission_id: int, data: AdmissionInterviewIn, db: Session = Depends(get_db)
):
    admission = _get_or_404(db, admission_id)
    interview = AdmissionInterview(admission_id=admission.id, **data.model_dump())
    db.add(interview)
    db.commit()
    db.refresh(interview)
    return interview


@interviews_router.put("/{interview_id}", response_model=AdmissionInterviewOut)
def update_interview(
    interview_id: int, data: AdmissionInterviewIn, db: Session = Depends(get_db)
):
    interview = _interview_or_404(db, interview_id)
    for key, value in data.model_dump().items():
        setattr(interview, key, value)
    db.commit()
    db.refresh(interview)
    return interview


@interviews_router.delete("/{interview_id}", status_code=204)
def delete_interview(interview_id: int, db: Session = Depends(get_db)):
    interview = _interview_or_404(db, interview_id)
    db.delete(interview)
    db.commit()


@router.get("/{admission_id}/scores", response_model=list[AdmissionScoreOut])
def list_scores(admission_id: int, db: Session = Depends(get_db)):
    admission = _get_or_404(db, admission_id)
    return db.scalars(
        select(AdmissionScore)
        .where(AdmissionScore.admission_id == admission.id)
        .order_by(AdmissionScore.criterion)
    ).all()


@router.post(
    "/{admission_id}/scores", response_model=AdmissionScoreOut, status_code=201
)
def create_score(
    admission_id: int, data: AdmissionScoreIn, db: Session = Depends(get_db)
):
    admission = _get_or_404(db, admission_id)
    score = AdmissionScore(admission_id=admission.id, **data.model_dump())
    db.add(score)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ya existe un puntaje para ese criterio"
        )
    db.refresh(score)
    return score


@scores_router.put("/{score_id}", response_model=AdmissionScoreOut)
def update_score(score_id: int, data: AdmissionScoreIn, db: Session = Depends(get_db)):
    score = _score_or_404(db, score_id)
    for key, value in data.model_dump().items():
        setattr(score, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ya existe un puntaje para ese criterio"
        )
    db.refresh(score)
    return score


@scores_router.delete("/{score_id}", status_code=204)
def delete_score(score_id: int, db: Session = Depends(get_db)):
    score = _score_or_404(db, score_id)
    db.delete(score)
    db.commit()
