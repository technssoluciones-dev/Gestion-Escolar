"""Carga datos de ejemplo para probar el sistema.

Uso:  python seed.py
"""
import random
from datetime import date

from app.database import Base, SessionLocal, engine
from app.main import ensure_admin
from app.models import Course, Guardian, Student, Teacher
from app.rut import calc_dv

random.seed(7)
FIRST = ["Sofía", "Mateo", "Valentina", "Benjamín", "Isidora", "Lucas", "Catalina", "Tomás",
         "Martina", "Agustín", "Javiera", "Vicente", "Emilia", "Joaquín", "Antonia", "Diego"]
LAST = ["González", "Muñoz", "Rojas", "Díaz", "Pérez", "Soto", "Contreras", "Silva",
        "Martínez", "Sepúlveda", "Morales", "Rodríguez", "López", "Fuentes", "Hernández", "Torres"]
SUBJECTS = ["Matemática", "Lenguaje", "Historia", "Ciencias", "Inglés", "Educación Física"]


def make_rut(base: int) -> str:
    return f"{base}-{calc_dv(str(base))}"


def run() -> None:
    Base.metadata.create_all(engine)
    ensure_admin()
    with SessionLocal() as db:
        if db.query(Course).first():
            print("Ya hay datos; no se cargó nada.")
            return

        teachers = []
        for i, subject in enumerate(SUBJECTS):
            t = Teacher(
                rut=make_rut(10_000_000 + i * 137_001),
                first_name=random.choice(FIRST), last_name=random.choice(LAST),
                email=f"profesor{i + 1}@colegio.cl", specialty=subject,
                hire_date=date(2015 + i, 3, 1),
            )
            teachers.append(t)
        db.add_all(teachers)
        db.flush()

        courses = []
        for i, name in enumerate(["1° Básico A", "1° Básico B", "2° Básico A", "3° Básico A"]):
            c = Course(name=name, level="Básica", year=2026, head_teacher_id=teachers[i].id)
            courses.append(c)
        db.add_all(courses)
        db.flush()

        for i in range(24):
            guardian = Guardian(
                rut=make_rut(8_000_000 + i * 91_003),
                first_name=random.choice(FIRST), last_name=random.choice(LAST),
                phone=f"+56 9 {random.randint(1000, 9999)} {random.randint(1000, 9999)}",
            )
            db.add(guardian)
            db.flush()
            course = courses[i % len(courses)]
            db.add(Student(
                rut=make_rut(22_000_000 + i * 53_011),
                first_name=random.choice(FIRST), last_name=guardian.last_name,
                birth_date=date(2026 - 6 - (i % len(courses)), random.randint(1, 12), random.randint(1, 28)),
                gender=random.choice(["F", "M"]),
                enrollment_date=date(2026, 3, 2),
                course_id=course.id, guardian_id=guardian.id,
            ))
        db.commit()
        print("Datos de ejemplo cargados: 6 profesores, 4 cursos, 24 estudiantes y 24 apoderados.")


if __name__ == "__main__":
    run()
