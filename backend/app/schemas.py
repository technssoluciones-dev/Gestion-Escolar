from datetime import date
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

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
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORM):
    id: int
    email: str
    full_name: str


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
    hire_date: date | None = None
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
    birth_date: date
    gender: Literal["F", "M", "O"] | None = None
    email: EmailStr | None = None
    address: str | None = None
    enrollment_date: date | None = None
    status: Literal["activo", "retirado"] = "activo"
    course_id: int | None = None
    guardian_id: int | None = None

    @field_validator("birth_date")
    @classmethod
    def check_birth(cls, v: date) -> date:
        if v > date.today():
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


# ---------- Panel ----------
class CourseCount(BaseModel):
    course: str
    students: int


class DashboardOut(BaseModel):
    students: int
    teachers: int
    guardians: int
    courses: int
    students_without_course: int
    per_course: list[CourseCount]
