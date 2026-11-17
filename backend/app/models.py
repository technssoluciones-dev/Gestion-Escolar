from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    """Usuario que entra al sistema (administración del colegio)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


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
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    head_courses: Mapped[list["Course"]] = relationship(back_populates="head_teacher")

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
    birth_date: Mapped[date] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(1), nullable=True)  # F, M, O
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enrollment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="activo")  # activo | retirado
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    guardian_id: Mapped[int | None] = mapped_column(ForeignKey("guardians.id"), nullable=True)

    course: Mapped[Course | None] = relationship(back_populates="students")
    guardian: Mapped[Guardian | None] = relationship(back_populates="students")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
