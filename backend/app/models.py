from datetime import date as DateType
from datetime import datetime, time as TimeType

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    """Usuario que entra al sistema.

    Los roles de personal (admin, secretaria, profesor) usan el panel. Los roles
    de portal (apoderado, estudiante) solo ven la información de sus estudiantes.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # admin | secretaria | profesor | apoderado | estudiante
    role: Mapped[str] = mapped_column(
        String(20), default="admin", server_default="admin", index=True
    )
    guardian_id: Mapped[int | None] = mapped_column(
        ForeignKey("guardians.id"), nullable=True
    )
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id"), nullable=True
    )
    teacher_id: Mapped[int | None] = mapped_column(
        ForeignKey("teachers.id"), nullable=True
    )

    guardian: Mapped["Guardian | None"] = relationship(foreign_keys=[guardian_id])
    student: Mapped["Student | None"] = relationship(foreign_keys=[student_id])
    teacher: Mapped["Teacher | None"] = relationship(foreign_keys=[teacher_id])

    @property
    def guardian_name(self) -> str | None:
        return self.guardian.full_name if self.guardian else None

    @property
    def student_name(self) -> str | None:
        return self.student.full_name if self.student else None

    @property
    def teacher_name(self) -> str | None:
        return self.teacher.full_name if self.teacher else None


class Guardian(Base):
    """Apoderado de un estudiante."""

    __tablename__ = "guardians"

    id: Mapped[int] = mapped_column(primary_key=True)
    rut: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    students: Mapped[list["Student"]] = relationship(back_populates="guardian")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(primary_key=True)
    rut: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    specialty: Mapped[str | None] = mapped_column(String(150), nullable=True)
    hire_date: Mapped[DateType | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    head_courses: Mapped[list["Course"]] = relationship(back_populates="head_teacher")
    course_subjects: Mapped[list["CourseSubject"]] = relationship(back_populates="teacher")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Course(Base):
    """Curso, por ejemplo '1° Básico A' del año 2026."""

    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("name", "year", name="uq_course_name_year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(50))  # Ej: Básica, Media, Parvularia
    year: Mapped[int] = mapped_column(Integer, index=True)
    capacity: Mapped[int] = mapped_column(Integer, default=45)
    head_teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True)

    head_teacher: Mapped[Teacher | None] = relationship(back_populates="head_courses")
    students: Mapped[list["Student"]] = relationship(back_populates="course")
    attendance: Mapped[list["Attendance"]] = relationship(back_populates="course")
    grades: Mapped[list["Grade"]] = relationship(back_populates="course")
    course_subjects: Mapped[list["CourseSubject"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )

    @property
    def student_count(self) -> int:
        return len([s for s in self.students if s.is_active])

    @property
    def head_teacher_name(self) -> str | None:
        return self.head_teacher.full_name if self.head_teacher else None


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    rut: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    birth_date: Mapped[DateType] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(1), nullable=True)  # F, M, O
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enrollment_date: Mapped[DateType | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="activo")  # activo | retirado
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    guardian_id: Mapped[int | None] = mapped_column(ForeignKey("guardians.id"), nullable=True)

    course: Mapped[Course | None] = relationship(back_populates="students")
    guardian: Mapped[Guardian | None] = relationship(back_populates="students")
    attendance: Mapped[list["Attendance"]] = relationship(back_populates="student")
    grades: Mapped[list["Grade"]] = relationship(back_populates="student")
    fees: Mapped[list["Fee"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Subject(Base):
    """Asignatura del plan de estudios (Matemática, Lenguaje, ...)."""

    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    grades: Mapped[list["Grade"]] = relationship(back_populates="subject")
    course_subjects: Mapped[list["CourseSubject"]] = relationship(back_populates="subject")


class Attendance(Base):
    """Asistencia de un estudiante en un día (un registro por estudiante y fecha)."""

    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("student_id", "date", name="uq_attendance_student_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    date: Mapped[DateType] = mapped_column(Date, index=True)
    # presente | ausente | atrasado | justificado
    status: Mapped[str] = mapped_column(String(20), default="presente")
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    student: Mapped[Student] = relationship(back_populates="attendance")
    course: Mapped[Course] = relationship(back_populates="attendance")


class Grade(Base):
    """Nota de una evaluación, en escala chilena de 1.0 a 7.0."""

    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    score: Mapped[float] = mapped_column(Numeric(3, 1))
    weight: Mapped[int] = mapped_column(Integer, default=1)  # ponderación relativa
    date: Mapped[DateType] = mapped_column(Date, index=True)
    evaluation_id: Mapped[int | None] = mapped_column(
        ForeignKey("evaluations.id"), nullable=True, index=True
    )

    student: Mapped[Student] = relationship(back_populates="grades")
    subject: Mapped[Subject] = relationship(back_populates="grades")
    course: Mapped[Course] = relationship(back_populates="grades")
    evaluation: Mapped["Evaluation | None"] = relationship(back_populates="grades")


class CourseSubject(Base):
    """Asignatura que se dicta en un curso, con el profesor que la imparte."""

    __tablename__ = "course_subjects"
    __table_args__ = (UniqueConstraint("course_id", "subject_id", name="uq_course_subject"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True, index=True)

    course: Mapped[Course] = relationship(back_populates="course_subjects")
    subject: Mapped[Subject] = relationship(back_populates="course_subjects")
    teacher: Mapped[Teacher | None] = relationship(back_populates="course_subjects")
    schedules: Mapped[list["ScheduleBlock"]] = relationship(
        back_populates="course_subject", cascade="all, delete-orphan"
    )
    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="course_subject", cascade="all, delete-orphan"
    )

    @property
    def schedule_count(self) -> int:
        return len(self.schedules)


class Evaluation(Base):
    """Evaluación formal de una asignatura de un curso (prueba, control, tarea...)."""

    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("course_subject_id", "title", name="uq_evaluation_title"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_subject_id: Mapped[int] = mapped_column(
        ForeignKey("course_subjects.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="prueba")
    date: Mapped[DateType] = mapped_column(Date, index=True)
    weight: Mapped[int] = mapped_column(Integer, default=1)

    course_subject: Mapped[CourseSubject] = relationship(back_populates="evaluations")
    grades: Mapped[list["Grade"]] = relationship(back_populates="evaluation")

    @property
    def course_id(self) -> int:
        return self.course_subject.course_id

    @property
    def course_name(self) -> str:
        return self.course_subject.course.name

    @property
    def subject_id(self) -> int:
        return self.course_subject.subject_id

    @property
    def subject_name(self) -> str:
        return self.course_subject.subject.name

    @property
    def teacher_name(self) -> str | None:
        teacher = self.course_subject.teacher
        return teacher.full_name if teacher else None

    @property
    def grade_count(self) -> int:
        return len(self.grades)


class ScheduleBlock(Base):
    """Bloque de horario semanal: una asignatura de un curso en un día y hora."""

    __tablename__ = "schedule_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_subject_id: Mapped[int] = mapped_column(
        ForeignKey("course_subjects.id"), index=True
    )
    weekday: Mapped[int] = mapped_column(Integer)  # 1 = lunes ... 5 = viernes
    start_time: Mapped[TimeType] = mapped_column(Time)
    end_time: Mapped[TimeType] = mapped_column(Time)
    room: Mapped[str | None] = mapped_column(String(50), nullable=True)

    course_subject: Mapped[CourseSubject] = relationship(back_populates="schedules")

    @property
    def course_id(self) -> int:
        return self.course_subject.course_id

    @property
    def course_name(self) -> str:
        return self.course_subject.course.name

    @property
    def subject_id(self) -> int:
        return self.course_subject.subject_id

    @property
    def subject_name(self) -> str:
        return self.course_subject.subject.name

    @property
    def teacher_id(self) -> int | None:
        return self.course_subject.teacher_id

    @property
    def teacher_name(self) -> str | None:
        teacher = self.course_subject.teacher
        return teacher.full_name if teacher else None


class Admission(Base):
    """Postulación de un nuevo estudiante al colegio."""

    __tablename__ = "admissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    applicant_rut: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    birth_date: Mapped[DateType] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(1), nullable=True)  # F, M, O
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    guardian_first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    guardian_last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    guardian_rut: Mapped[str | None] = mapped_column(String(12), nullable=True)
    guardian_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guardian_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    # postulada | en_revision | aceptada | rechazada | matriculada
    status: Mapped[str] = mapped_column(String(20), default="postulada", index=True)
    application_date: Mapped[DateType] = mapped_column(Date, default=DateType.today)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id"), nullable=True, unique=True
    )
    # Token que permite a la familia seguir y completar su postulación en línea.
    access_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )

    course: Mapped[Course | None] = relationship()
    student: Mapped[Student | None] = relationship()
    documents: Mapped[list["AdmissionDocument"]] = relationship(
        cascade="all, delete-orphan", back_populates="admission"
    )
    interviews: Mapped[list["AdmissionInterview"]] = relationship(
        cascade="all, delete-orphan", back_populates="admission"
    )
    scores: Mapped[list["AdmissionScore"]] = relationship(
        cascade="all, delete-orphan", back_populates="admission"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def student_name(self) -> str | None:
        return self.student.full_name if self.student else None


class AdmissionDocument(Base):
    """Archivo adjunto a una postulación (certificado, ficha médica, etc.)."""

    __tablename__ = "admission_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    admission_id: Mapped[int] = mapped_column(
        ForeignKey("admissions.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(150))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    admission: Mapped[Admission] = relationship(back_populates="documents")


class AdmissionInterview(Base):
    """Entrevista del proceso de admisión."""

    __tablename__ = "admission_interviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    admission_id: Mapped[int] = mapped_column(
        ForeignKey("admissions.id"), index=True, nullable=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    interviewer: Mapped[str] = mapped_column(String(150))
    # presencial | online | telefonica
    mode: Mapped[str] = mapped_column(String(20), default="presencial")
    # pendiente | realizada | cancelada
    status: Mapped[str] = mapped_column(String(20), default="pendiente")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    admission: Mapped[Admission] = relationship(back_populates="interviews")


class AdmissionScore(Base):
    """Puntaje de un criterio de evaluación de la postulación (0 a 100)."""

    __tablename__ = "admission_scores"
    __table_args__ = (
        UniqueConstraint("admission_id", "criterion", name="uq_admission_criterion"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    admission_id: Mapped[int] = mapped_column(
        ForeignKey("admissions.id"), index=True, nullable=False
    )
    criterion: Mapped[str] = mapped_column(String(100))
    score: Mapped[float] = mapped_column(Numeric(5, 1))
    weight: Mapped[int] = mapped_column(Integer, default=1)
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)

    admission: Mapped[Admission] = relationship(back_populates="scores")


class Fee(Base):
    """Cobro del colegio a un estudiante: matrícula, mensualidad, cuota u otro."""

    __tablename__ = "fees"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    # matricula | mensualidad | cuota | otro
    concept: Mapped[str] = mapped_column(String(20), index=True)
    description: Mapped[str | None] = mapped_column(String(120), nullable=True)
    period: Mapped[str] = mapped_column(String(7), index=True)  # Ej: 2026-03
    amount: Mapped[int] = mapped_column(Integer)  # pesos chilenos, sin decimales
    due_date: Mapped[DateType] = mapped_column(Date, index=True)

    student: Mapped[Student] = relationship(back_populates="fees")
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="fee", cascade="all, delete-orphan", order_by="Payment.paid_on"
    )
    online_intents: Mapped[list["PaymentIntent"]] = relationship(
        back_populates="fee", cascade="all, delete-orphan"
    )

    @property
    def paid_amount(self) -> int:
        return sum(payment.amount for payment in self.payments)

    @property
    def balance(self) -> int:
        return max(self.amount - self.paid_amount, 0)

    @property
    def status(self) -> str:
        if self.balance <= 0:
            return "pagada"
        if self.due_date < DateType.today():
            return "vencida"
        if self.paid_amount > 0:
            return "parcial"
        return "pendiente"

    @property
    def student_name(self) -> str:
        return self.student.full_name

    @property
    def student_rut(self) -> str:
        return self.student.rut

    @property
    def course_id(self) -> int | None:
        return self.student.course_id

    @property
    def course_name(self) -> str | None:
        return self.student.course.name if self.student.course else None


class Payment(Base):
    """Abono de un cobro. Un cobro puede pagarse en varias cuotas."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    fee_id: Mapped[int] = mapped_column(ForeignKey("fees.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    paid_on: Mapped[DateType] = mapped_column(Date, default=DateType.today, index=True)
    # efectivo | transferencia | tarjeta | cheque | otro
    method: Mapped[str] = mapped_column(String(20), default="transferencia")
    reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    fee: Mapped[Fee] = relationship(back_populates="payments")


class PaymentIntent(Base):
    """Intento de pago en línea de un cobro, con su token de checkout."""

    __tablename__ = "payment_intents"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    fee_id: Mapped[int] = mapped_column(ForeignKey("fees.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    # sandbox | webpay
    provider: Mapped[str] = mapped_column(String(20), default="sandbox")
    # pendiente | pagada | cancelada
    status: Mapped[str] = mapped_column(String(20), default="pendiente", index=True)
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id"), nullable=True
    )
    gateway_token: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )
    gateway_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)

    fee: Mapped[Fee] = relationship(back_populates="online_intents")
    payment: Mapped[Payment | None] = relationship()

    @property
    def student_id(self) -> int:
        return self.fee.student_id

    @property
    def student_name(self) -> str:
        return self.fee.student.full_name

    @property
    def student_rut(self) -> str:
        return self.fee.student.rut

    @property
    def course_name(self) -> str | None:
        course = self.fee.student.course
        return course.name if course else None

    @property
    def concept(self) -> str:
        return self.fee.concept

    @property
    def description(self) -> str | None:
        return self.fee.description

    @property
    def period(self) -> str:
        return self.fee.period

    @property
    def due_date(self) -> DateType:
        return self.fee.due_date

    @property
    def fee_amount(self) -> int:
        return self.fee.amount

    @property
    def fee_paid(self) -> int:
        return self.fee.paid_amount

    @property
    def fee_balance(self) -> int:
        return self.fee.balance

    @property
    def fee_status(self) -> str:
        return self.fee.status


class BankMovement(Base):
    """Abono importado desde la cartola bancaria y su conciliación con un cobro."""

    __tablename__ = "bank_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    movement_date: Mapped[DateType] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(200))
    reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    amount: Mapped[int] = mapped_column(Integer)
    # pendiente | conciliado
    status: Mapped[str] = mapped_column(String(20), default="pendiente", index=True)
    fee_id: Mapped[int | None] = mapped_column(
        ForeignKey("fees.id"), nullable=True, index=True
    )
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    fee: Mapped[Fee | None] = relationship()
    payment: Mapped[Payment | None] = relationship()

    @property
    def student_name(self) -> str | None:
        return self.fee.student.full_name if self.fee else None

    @property
    def student_rut(self) -> str | None:
        return self.fee.student.rut if self.fee else None

    @property
    def fee_period(self) -> str | None:
        return self.fee.period if self.fee else None

    @property
    def fee_concept(self) -> str | None:
        return self.fee.concept if self.fee else None



class Notification(Base):
    """Aviso del colegio a la familia de un estudiante (asistencia, notas o deuda)."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_notification_dedupe"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    guardian_id: Mapped[int | None] = mapped_column(
        ForeignKey("guardians.id"), nullable=True, index=True
    )
    # inasistencia | notas | deuda | general
    type: Mapped[str] = mapped_column(String(20), default="general", index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)  # AAAA-MM
    title: Mapped[str] = mapped_column(String(150))
    message: Mapped[str] = mapped_column(String(500))
    # pendiente | enviada
    status: Mapped[str] = mapped_column(String(20), default="pendiente", index=True)
    # manual | email | whatsapp
    channel: Mapped[str] = mapped_column(String(20), default="manual")
    # Evita duplicados al generar avisos del mismo tipo y período.
    dedupe_key: Mapped[str | None] = mapped_column(
        String(80), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)

    student: Mapped[Student] = relationship()
    guardian: Mapped["Guardian | None"] = relationship()

    @property
    def student_name(self) -> str:
        return self.student.full_name

    @property
    def student_rut(self) -> str:
        return self.student.rut

    @property
    def course_name(self) -> str | None:
        return self.student.course.name if self.student.course else None

    @property
    def guardian_name(self) -> str | None:
        return self.guardian.full_name if self.guardian else None

    @property
    def guardian_email(self) -> str | None:
        return self.guardian.email if self.guardian else None

    @property
    def guardian_phone(self) -> str | None:
        return self.guardian.phone if self.guardian else None



class CertificateSignature(Base):
    """Firma electrónica (HMAC-SHA256) de un certificado emitido."""

    __tablename__ = "certificate_signatures"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    certificate_number: Mapped[str] = mapped_column(String(40))
    issued_on: Mapped[DateType] = mapped_column(Date)
    payload: Mapped[str] = mapped_column(Text)
    signature: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
