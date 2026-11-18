import re
from datetime import date as DateType
from datetime import datetime, time as TimeType
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .rut import normalize_rut

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int


class RutMixin(BaseModel):
    rut: str

    @field_validator("rut")
    @classmethod
    def check_rut(cls, v: str) -> str:
        return normalize_rut(v)


# ---------- Auth ----------
UserRole = Literal["admin", "secretaria", "profesor", "apoderado", "estudiante"]


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    full_name: str
    email: str


class UserOut(ORM):
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    guardian_id: int | None = None
    student_id: int | None = None
    teacher_id: int | None = None
    guardian_name: str | None = None
    student_name: str | None = None
    teacher_name: str | None = None


class UserIn(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=8)
    role: UserRole = "secretaria"
    is_active: bool = True
    guardian_id: int | None = None
    student_id: int | None = None
    teacher_id: int | None = None

    @field_validator("full_name")
    @classmethod
    def check_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        return v

    @model_validator(mode="after")
    def check_links(self):
        if self.role == "apoderado" and self.guardian_id is None:
            raise ValueError("Un usuario apoderado debe estar asociado a un apoderado")
        if self.role == "estudiante" and self.student_id is None:
            raise ValueError("Un usuario estudiante debe estar asociado a un estudiante")
        return self


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    password: str | None = Field(default=None, min_length=8)
    role: UserRole | None = None
    is_active: bool | None = None
    guardian_id: int | None = None
    student_id: int | None = None
    teacher_id: int | None = None


# ---------- Apoderados ----------
class GuardianBase(RutMixin):
    first_name: str
    last_name: str
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None


class GuardianIn(GuardianBase):
    pass


class GuardianOut(ORM, GuardianBase):
    id: int
    full_name: str


class GuardianMini(ORM):
    id: int
    full_name: str
    phone: str | None = None


# ---------- Profesores ----------
class TeacherBase(RutMixin):
    first_name: str
    last_name: str
    email: EmailStr | None = None
    phone: str | None = None
    specialty: str | None = None
    hire_date: DateType | None = None
    is_active: bool = True


class TeacherIn(TeacherBase):
    pass


class TeacherMini(ORM):
    id: int
    full_name: str


class CourseMini(ORM):
    id: int
    name: str
    year: int


class TeacherOut(ORM, TeacherBase):
    id: int
    full_name: str
    head_courses: list[CourseMini] = []


# ---------- Cursos ----------
class CourseBase(BaseModel):
    name: str
    level: str
    year: int
    capacity: int = 45
    head_teacher_id: int | None = None

    @field_validator("capacity")
    @classmethod
    def check_capacity(cls, v: int) -> int:
        if v < 1:
            raise ValueError("La capacidad debe ser al menos 1")
        return v


class CourseIn(CourseBase):
    pass


class CourseOut(ORM, CourseBase):
    id: int
    student_count: int
    head_teacher_name: str | None = None


# ---------- Estudiantes ----------
class StudentBase(RutMixin):
    first_name: str
    last_name: str
    birth_date: DateType
    gender: Literal["F", "M", "O"] | None = None
    email: EmailStr | None = None
    address: str | None = None
    enrollment_date: DateType | None = None
    status: Literal["activo", "retirado"] = "activo"
    course_id: int | None = None
    guardian_id: int | None = None

    @field_validator("birth_date")
    @classmethod
    def check_birth(cls, v: DateType) -> DateType:
        if v > DateType.today():
            raise ValueError("La fecha de nacimiento no puede ser futura")
        return v


class StudentIn(StudentBase):
    pass


class StudentOut(ORM, StudentBase):
    id: int
    full_name: str
    is_active: bool
    course: CourseMini | None = None
    guardian: GuardianMini | None = None


# ---------- Asignaturas ----------
class SubjectBase(BaseModel):
    name: str
    code: str | None = None

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre de la asignatura no puede estar vacío")
        return v

    @field_validator("code")
    @classmethod
    def check_code(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip().upper() or None


class SubjectIn(SubjectBase):
    pass


class SubjectOut(ORM, SubjectBase):
    id: int


# ---------- Horarios ----------
class CourseSubjectIn(BaseModel):
    course_id: int
    subject_id: int
    teacher_id: int | None = None


class CourseSubjectOut(ORM):
    id: int
    course_id: int
    subject_id: int
    teacher_id: int | None = None
    subject: SubjectOut
    teacher: TeacherMini | None = None
    schedule_count: int


class ScheduleIn(BaseModel):
    course_subject_id: int
    weekday: int
    start_time: TimeType
    end_time: TimeType
    room: str | None = None

    @field_validator("weekday")
    @classmethod
    def check_weekday(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError("El día debe estar entre lunes (1) y viernes (5)")
        return v

    @field_validator("room")
    @classmethod
    def check_room(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None

    @model_validator(mode="after")
    def check_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("La hora de término debe ser posterior a la de inicio")
        return self


class ScheduleOut(ORM):
    id: int
    course_subject_id: int
    course_id: int
    course_name: str
    subject_id: int
    subject_name: str
    teacher_id: int | None = None
    teacher_name: str | None = None
    weekday: int
    start_time: TimeType
    end_time: TimeType
    room: str | None = None


# ---------- Asistencia ----------
AttendanceStatus = Literal["presente", "ausente", "atrasado", "justificado"]


class AttendanceItemIn(BaseModel):
    student_id: int
    status: AttendanceStatus | None = None
    note: str | None = None


class AttendanceDayIn(BaseModel):
    course_id: int
    date: DateType
    items: list[AttendanceItemIn] = []

    @field_validator("date")
    @classmethod
    def check_date(cls, v: DateType) -> DateType:
        if v > DateType.today():
            raise ValueError("No se puede registrar asistencia de un día futuro")
        return v


class AttendanceRowOut(BaseModel):
    student_id: int
    full_name: str
    rut: str
    status: AttendanceStatus | None = None
    note: str | None = None
    record_id: int | None = None


class AttendanceDaySummary(BaseModel):
    presente: int = 0
    ausente: int = 0
    atrasado: int = 0
    justificado: int = 0
    sin_marcar: int = 0


class AttendanceDayOut(BaseModel):
    course: CourseMini
    date: DateType
    items: list[AttendanceRowOut]
    summary: AttendanceDaySummary


class AttendanceSummaryRow(BaseModel):
    student_id: int
    full_name: str
    rut: str
    presente: int = 0
    ausente: int = 0
    atrasado: int = 0
    justificado: int = 0
    total: int = 0
    rate: float | None = None


class AttendancePeriodSummary(BaseModel):
    presente: int = 0
    ausente: int = 0
    atrasado: int = 0
    justificado: int = 0
    total: int = 0
    rate: float | None = None


class AttendanceSummaryOut(BaseModel):
    course: CourseMini
    from_date: DateType
    to_date: DateType
    days: int
    items: list[AttendanceSummaryRow]
    summary: AttendancePeriodSummary


class AttendanceTodayOut(BaseModel):
    date: DateType
    marked: int = 0
    presente: int = 0
    ausente: int = 0
    atrasado: int = 0
    justificado: int = 0
    unmarked: int = 0
    rate: float | None = None


# ---------- Evaluaciones ----------
EvaluationKind = Literal["prueba", "control", "tarea", "proyecto", "examen", "otro"]


class EvaluationBase(BaseModel):
    course_subject_id: int
    title: str
    kind: EvaluationKind = "prueba"
    date: DateType
    weight: int = 1

    @field_validator("title")
    @classmethod
    def check_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre de la evaluación no puede estar vacío")
        return v

    @field_validator("weight")
    @classmethod
    def check_weight(cls, v: int) -> int:
        if v < 1:
            raise ValueError("La ponderación debe ser al menos 1")
        return v


class EvaluationIn(EvaluationBase):
    pass


class EvaluationOut(ORM):
    id: int
    course_subject_id: int
    course_id: int
    course_name: str
    subject_id: int
    subject_name: str
    teacher_name: str | None = None
    title: str
    kind: EvaluationKind
    date: DateType
    weight: int
    grade_count: int = 0


# ---------- Notas ----------
class GradeBase(BaseModel):
    student_id: int
    subject_id: int
    title: str
    score: float
    weight: int = 1
    date: DateType
    evaluation_id: int | None = None

    @field_validator("score")
    @classmethod
    def check_score(cls, v: float) -> float:
        if not 1.0 <= v <= 7.0:
            raise ValueError("La nota debe estar entre 1.0 y 7.0")
        return round(v, 1)

    @field_validator("weight")
    @classmethod
    def check_weight(cls, v: int) -> int:
        if v < 1:
            raise ValueError("La ponderación debe ser al menos 1")
        return v

    @field_validator("title")
    @classmethod
    def check_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre de la evaluación no puede estar vacío")
        return v


class GradeIn(GradeBase):
    pass


class GradeOut(ORM):
    id: int
    student_id: int
    subject_id: int
    title: str
    score: float
    weight: int
    date: DateType
    evaluation_id: int | None = None


class GradeBulkItem(BaseModel):
    student_id: int
    score: float

    @field_validator("score")
    @classmethod
    def check_score(cls, v: float) -> float:
        if not 1.0 <= v <= 7.0:
            raise ValueError("La nota debe estar entre 1.0 y 7.0")
        return round(v, 1)


class GradeBulkIn(BaseModel):
    course_id: int
    subject_id: int
    title: str
    date: DateType
    weight: int = 1
    evaluation_id: int | None = None
    items: list[GradeBulkItem] = []

    @field_validator("title")
    @classmethod
    def check_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre de la evaluación no puede estar vacío")
        return v

    @field_validator("weight")
    @classmethod
    def check_weight(cls, v: int) -> int:
        if v < 1:
            raise ValueError("La ponderación debe ser al menos 1")
        return v


class GradeBulkOut(BaseModel):
    created: int


class StudentGradeRow(BaseModel):
    student_id: int
    full_name: str
    rut: str
    grades: list[GradeOut]
    average: float | None = None
    count: int


class GradeSummary(BaseModel):
    average: float | None = None
    approved: int = 0
    failed: int = 0
    without_grades: int = 0
    grade_count: int = 0


class GradeReportOut(BaseModel):
    course: CourseMini
    subject: SubjectOut
    items: list[StudentGradeRow]
    summary: GradeSummary


class SubjectAverage(BaseModel):
    subject_id: int
    average: float | None = None
    count: int = 0


class StudentMatrixRow(BaseModel):
    student_id: int
    full_name: str
    rut: str
    averages: list[SubjectAverage]
    overall: float | None = None


class GradeMatrixOut(BaseModel):
    course: CourseMini
    subjects: list[SubjectOut]
    items: list[StudentMatrixRow]
    subject_averages: list[SubjectAverage]
    summary: GradeSummary


class StudentSubjectRow(BaseModel):
    subject: SubjectOut
    grades: list[GradeOut]
    average: float | None = None
    count: int


class StudentGradesOut(BaseModel):
    student_id: int
    full_name: str
    rut: str
    items: list[StudentSubjectRow]
    overall: float | None = None


# ---------- Admisiones ----------
AdmissionStatus = Literal[
    "postulada", "en_revision", "aceptada", "rechazada", "matriculada"
]


class AdmissionBase(BaseModel):
    applicant_rut: str
    first_name: str
    last_name: str
    birth_date: DateType
    gender: Literal["F", "M", "O"] | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None

    guardian_first_name: str | None = None
    guardian_last_name: str | None = None
    guardian_rut: str | None = None
    guardian_email: EmailStr | None = None
    guardian_phone: str | None = None

    course_id: int | None = None
    year: int
    status: AdmissionStatus = "postulada"
    application_date: DateType = Field(default_factory=DateType.today)
    notes: str | None = None

    @field_validator("applicant_rut")
    @classmethod
    def check_applicant_rut(cls, v: str) -> str:
        return normalize_rut(v)

    @field_validator("guardian_rut")
    @classmethod
    def check_guardian_rut(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        return normalize_rut(v)

    @field_validator("first_name", "last_name")
    @classmethod
    def check_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        return v

    @field_validator("birth_date")
    @classmethod
    def check_birth(cls, v: DateType) -> DateType:
        if v > DateType.today():
            raise ValueError("La fecha de nacimiento no puede ser futura")
        return v

    @field_validator("year")
    @classmethod
    def check_year(cls, v: int) -> int:
        if not 1900 <= v <= 2100:
            raise ValueError("El año no es válido")
        return v

    @field_validator("notes")
    @classmethod
    def check_notes(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None

    @model_validator(mode="after")
    def check_guardian(self):
        if self.guardian_rut and not (self.guardian_first_name and self.guardian_last_name):
            raise ValueError(
                "Si indicas RUT del apoderado, indica también su nombre y apellido"
            )
        return self


class AdmissionIn(AdmissionBase):
    pass


class AdmissionOut(ORM):
    id: int
    applicant_rut: str
    full_name: str
    first_name: str
    last_name: str
    birth_date: DateType
    gender: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    guardian_first_name: str | None = None
    guardian_last_name: str | None = None
    guardian_rut: str | None = None
    guardian_email: str | None = None
    guardian_phone: str | None = None
    course_id: int | None = None
    course: CourseMini | None = None
    year: int
    status: AdmissionStatus
    application_date: DateType
    notes: str | None = None
    student_id: int | None = None
    student_name: str | None = None


class AdmissionEnrollIn(BaseModel):
    course_id: int | None = None


# Expediente de admisión: documentos, entrevistas y puntajes
InterviewMode = Literal["presencial", "online", "telefonica"]
InterviewStatus = Literal["pendiente", "realizada", "cancelada"]


class AdmissionDocumentOut(ORM):
    id: int
    admission_id: int
    name: str
    filename: str
    content_type: str
    size: int
    uploaded_at: datetime


class AdmissionInterviewIn(BaseModel):
    scheduled_at: datetime
    interviewer: str
    mode: InterviewMode = "presencial"
    status: InterviewStatus = "pendiente"
    notes: str | None = None

    @field_validator("interviewer")
    @classmethod
    def check_interviewer(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Indica quién realizará la entrevista")
        return v

    @field_validator("notes")
    @classmethod
    def check_notes(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class AdmissionInterviewOut(ORM):
    id: int
    admission_id: int
    scheduled_at: datetime
    interviewer: str
    mode: InterviewMode
    status: InterviewStatus
    notes: str | None = None
    created_at: datetime


class AdmissionScoreIn(BaseModel):
    criterion: str
    score: float = Field(ge=0, le=100)
    weight: int = Field(default=1, ge=1, le=10)
    notes: str | None = None

    @field_validator("criterion")
    @classmethod
    def check_criterion(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El criterio no puede estar vacío")
        return v

    @field_validator("notes")
    @classmethod
    def check_notes(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class AdmissionScoreOut(ORM):
    id: int
    admission_id: int
    criterion: str
    score: float
    weight: int
    notes: str | None = None


class AdmissionDossierOut(BaseModel):
    documents: list[AdmissionDocumentOut]
    interviews: list[AdmissionInterviewOut]
    scores: list[AdmissionScoreOut]
    weighted_score: float | None = None


# Postulación en línea (portal público)
class PublicCourseOut(BaseModel):
    id: int
    name: str
    level: str | None = None
    year: int
    capacity: int
    vacancies: int


class PublicAdmissionIn(AdmissionBase):
    status: Literal["postulada"] = "postulada"
    year: int = Field(default_factory=lambda: DateType.today().year)

    @model_validator(mode="after")
    def check_contact(self):
        if not (self.guardian_first_name and self.guardian_last_name):
            raise ValueError("Indica el nombre y apellido del apoderado")
        if not (self.guardian_email or self.guardian_phone):
            raise ValueError("Indica un correo o teléfono de contacto del apoderado")
        return self


class PublicAdmissionOut(BaseModel):
    token: str
    status: AdmissionStatus
    applicant_name: str
    course_name: str | None = None
    year: int
    application_date: DateType
    documents: list[AdmissionDocumentOut] = []


class PublicAdmissionCreatedOut(PublicAdmissionOut):
    tracking_url: str



# ---------- Pagos ----------
FeeConcept = Literal["matricula", "mensualidad", "cuota", "otro"]
FeeStatus = Literal["pendiente", "parcial", "pagada", "vencida"]
PaymentMethod = Literal["efectivo", "transferencia", "tarjeta", "cheque", "otro"]
PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class FeeBase(BaseModel):
    student_id: int
    concept: FeeConcept
    description: str | None = None
    period: str
    amount: int
    due_date: DateType

    @field_validator("period")
    @classmethod
    def check_period(cls, v: str) -> str:
        import re

        if not re.fullmatch(PERIOD_PATTERN, v.strip()):
            raise ValueError("El período debe tener el formato AAAA-MM, por ejemplo 2026-03")
        return v.strip()

    @field_validator("amount")
    @classmethod
    def check_amount(cls, v: int) -> int:
        if v < 1:
            raise ValueError("El monto debe ser mayor que cero")
        return v

    @field_validator("description")
    @classmethod
    def check_description(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class FeeIn(FeeBase):
    pass


class PaymentIn(BaseModel):
    amount: int
    paid_on: DateType = Field(default_factory=DateType.today)
    method: PaymentMethod = "transferencia"
    reference: str | None = None
    note: str | None = None

    @field_validator("amount")
    @classmethod
    def check_amount(cls, v: int) -> int:
        if v < 1:
            raise ValueError("El monto del pago debe ser mayor que cero")
        return v

    @field_validator("paid_on")
    @classmethod
    def check_paid_on(cls, v: DateType) -> DateType:
        if v > DateType.today():
            raise ValueError("La fecha de pago no puede ser futura")
        return v

    @field_validator("reference", "note")
    @classmethod
    def check_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class PaymentOut(ORM):
    id: int
    fee_id: int
    amount: int
    paid_on: DateType
    method: PaymentMethod
    reference: str | None = None
    note: str | None = None


PaymentIntentStatus = Literal["pendiente", "pagada", "cancelada"]


class PaymentCheckoutIn(BaseModel):
    fee_id: int


class PaymentIntentOut(ORM):
    id: int
    token: str
    fee_id: int
    amount: int
    provider: str
    status: PaymentIntentStatus
    payment_id: int | None = None
    created_at: datetime
    paid_at: datetime | None = None
    student_id: int
    student_name: str
    student_rut: str
    course_name: str | None = None
    concept: FeeConcept
    description: str | None = None
    period: str
    due_date: DateType
    fee_amount: int
    fee_paid: int
    fee_balance: int
    fee_status: FeeStatus


class PaymentCheckoutOut(BaseModel):
    intent: PaymentIntentOut
    checkout_url: str
    provider: str = "sandbox"
    webpay_url: str | None = None
    webpay_token: str | None = None


class BankMovementOut(ORM):
    id: int
    movement_date: DateType
    description: str
    reference: str | None = None
    amount: int
    status: Literal["pendiente", "conciliado"]
    fee_id: int | None = None
    payment_id: int | None = None
    student_name: str | None = None
    student_rut: str | None = None
    fee_period: str | None = None
    fee_concept: FeeConcept | None = None
    created_at: datetime


class BankImportOut(BaseModel):
    imported: int = 0
    matched: int = 0
    pending: int = 0
    skipped: int = 0


class BankMatchIn(BaseModel):
    fee_id: int



class FeeOut(ORM):
    id: int
    student_id: int
    student_name: str
    student_rut: str
    course_id: int | None = None
    course_name: str | None = None
    concept: FeeConcept
    description: str | None = None
    period: str
    amount: int
    paid_amount: int
    balance: int
    due_date: DateType
    status: FeeStatus
    payments: list[PaymentOut] = []


class FeeSummaryOut(BaseModel):
    charged: int = 0
    collected: int = 0
    pending: int = 0
    overdue: int = 0
    paid_count: int = 0
    pending_count: int = 0
    overdue_count: int = 0


class FeeGenerateIn(BaseModel):
    course_id: int
    concept: FeeConcept = "mensualidad"
    period: str
    amount: int
    due_date: DateType
    description: str | None = None

    @field_validator("period")
    @classmethod
    def check_period(cls, v: str) -> str:
        import re

        if not re.fullmatch(PERIOD_PATTERN, v.strip()):
            raise ValueError("El período debe tener el formato AAAA-MM, por ejemplo 2026-03")
        return v.strip()

    @field_validator("amount")
    @classmethod
    def check_amount(cls, v: int) -> int:
        if v < 1:
            raise ValueError("El monto debe ser mayor que cero")
        return v


class FeeGenerateOut(BaseModel):
    created: int
    skipped: int


# ---------- Portal ----------
class PortalStudentOut(ORM):
    id: int
    full_name: str
    rut: str
    birth_date: DateType
    status: str
    course: CourseMini | None = None


class PortalMeOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    guardian: GuardianMini | None = None
    student: PortalStudentOut | None = None


class PortalAttendanceOut(BaseModel):
    from_date: DateType
    to_date: DateType
    total: int = 0
    presente: int = 0
    ausente: int = 0
    atrasado: int = 0
    justificado: int = 0
    rate: float | None = None


class PortalSubjectRow(BaseModel):
    subject: SubjectOut
    grades: list[GradeOut]
    average: float | None = None
    count: int


class PortalOverviewOut(BaseModel):
    student: PortalStudentOut
    attendance: PortalAttendanceOut
    subjects: list[PortalSubjectRow]
    overall: float | None = None
    fees: list[FeeOut]
    pending_amount: int = 0
    overdue_amount: int = 0


# ---------- Notificaciones ----------
NotificationType = Literal["inasistencia", "notas", "deuda", "general"]
NotificationStatus = Literal["pendiente", "enviada"]


class NotificationOut(ORM):
    id: int
    student_id: int
    guardian_id: int | None = None
    type: NotificationType
    period: str
    title: str
    message: str
    status: NotificationStatus
    channel: str
    created_at: datetime
    sent_at: datetime | None = None
    student_name: str
    student_rut: str
    course_name: str | None = None
    guardian_name: str | None = None
    guardian_email: str | None = None
    guardian_phone: str | None = None


class NotificationGenerateIn(BaseModel):
    period: str | None = None
    types: list[NotificationType] = ["inasistencia", "notas", "deuda"]

    @field_validator("period")
    @classmethod
    def check_period(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", v):
            raise ValueError("El período debe tener el formato AAAA-MM")
        return v


class NotificationGenerateOut(BaseModel):
    created: int
    skipped: int
    by_type: dict[str, int]


class NotificationIn(BaseModel):
    student_id: int
    title: str
    message: str
    type: NotificationType = "general"
    period: str | None = None

    @field_validator("title", "message")
    @classmethod
    def check_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El texto no puede estar vacío")
        return v

    @field_validator("period")
    @classmethod
    def check_period(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", v):
            raise ValueError("El período debe tener el formato AAAA-MM")
        return v


class NotificationUpdate(BaseModel):
    status: NotificationStatus


class NotificationSummaryOut(BaseModel):
    pending: int = 0
    sent: int = 0
    by_type: dict[str, int] = {}


# ---------- Panel ----------
class CourseCount(BaseModel):
    course: str
    students: int


class DashboardOut(BaseModel):
    students: int
    teachers: int
    guardians: int
    courses: int
    subjects: int
    pending_admissions: int
    students_without_course: int
    fees_pending: int = 0
    fees_overdue: int = 0
    attendance_today: AttendanceTodayOut
    per_course: list[CourseCount]
