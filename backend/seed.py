"""Carga datos de ejemplo para probar el sistema.

Uso:  python seed.py
"""
import random
from datetime import date, time, timedelta

from app.database import Base, SessionLocal, engine
from app.main import ensure_admin
from app.models import (
    Admission,
    Attendance,
    Course,
    CourseSubject,
    Evaluation,
    Fee,
    Grade,
    Guardian,
    Payment,
    ScheduleBlock,
    Student,
    Subject,
    Teacher,
    User,
)
from app.rut import calc_dv
from app.security import hash_password

random.seed(7)
FIRST = ["Sofía", "Mateo", "Valentina", "Benjamín", "Isidora", "Lucas", "Catalina", "Tomás",
         "Martina", "Agustín", "Javiera", "Vicente", "Emilia", "Joaquín", "Antonia", "Diego"]
LAST = ["González", "Muñoz", "Rojas", "Díaz", "Pérez", "Soto", "Contreras", "Silva",
        "Martínez", "Sepúlveda", "Morales", "Rodríguez", "López", "Fuentes", "Hernández", "Torres"]
SUBJECTS = ["Matemática", "Lenguaje", "Historia", "Ciencias", "Inglés", "Educación Física"]
CODES = ["MAT", "LEN", "HIS", "CIE", "ING", "EFI"]
ATTENDANCE_WEIGHTS = [
    ("presente", 0.88),
    ("ausente", 0.05),
    ("atrasado", 0.04),
    ("justificado", 0.03),
]
SCHOOL_SLOTS = [
    (time(8, 0), time(9, 30)),
    (time(9, 45), time(11, 15)),
    (time(11, 30), time(13, 0)),
    (time(14, 0), time(15, 30)),
    (time(15, 45), time(17, 15)),
]


def make_rut(base: int) -> str:
    return f"{base}-{calc_dv(str(base))}"


def random_status() -> str:
    value = random.random()
    cumulative = 0.0
    for status, weight in ATTENDANCE_WEIGHTS:
        cumulative += weight
        if value <= cumulative:
            return status
    return "presente"


def month_period(months_back: int) -> tuple[str, date]:
    today = date.today()
    year, month = today.year, today.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return f"{year}-{month:02d}", date(year, month, 5)


def last_weekdays(count: int) -> list[date]:
    days: list[date] = []
    cursor = date.today()
    while len(days) < count:
        if cursor.weekday() < 5:  # lunes a viernes
            days.append(cursor)
        cursor -= timedelta(days=1)
    return days


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
            c = Course(name=name, level="Básica", year=date.today().year, head_teacher_id=teachers[i].id)
            courses.append(c)
        db.add_all(courses)
        db.flush()

        subjects = [Subject(name=name, code=code) for name, code in zip(SUBJECTS, CODES)]
        db.add_all(subjects)
        db.flush()

        # Cada curso dicta todas las asignaturas, con un profesor a cargo.
        assignments: dict[tuple[int, int], CourseSubject] = {}
        for course_index, course in enumerate(courses):
            for subject_index, subject in enumerate(subjects):
                course_subject = CourseSubject(
                    course_id=course.id,
                    subject_id=subject.id,
                    teacher_id=teachers[(subject_index + course_index) % len(teachers)].id,
                )
                assignments[(course.id, subject.id)] = course_subject
                db.add(course_subject)
        db.flush()

        # Horario semanal: dos bloques por día, sin choques de curso, profesor ni sala.
        teacher_busy: set[tuple[int, int, int]] = set()
        course_busy: set[tuple[int, int, int]] = set()
        schedule_count = 0
        for course_index, course in enumerate(courses):
            for weekday in range(1, 6):
                for block in range(2):
                    subject = subjects[(course_index + (weekday - 1) * 2 + block * 3) % len(subjects)]
                    course_subject = assignments[(course.id, subject.id)]
                    rotation = (course_index + weekday + block) % len(SCHOOL_SLOTS)
                    slot_order = list(range(rotation, len(SCHOOL_SLOTS))) + list(range(rotation))
                    for slot_index in slot_order:
                        teacher_key = (course_subject.teacher_id, weekday, slot_index)
                        course_key = (course.id, weekday, slot_index)
                        if teacher_key in teacher_busy or course_key in course_busy:
                            continue
                        start, end = SCHOOL_SLOTS[slot_index]
                        db.add(
                            ScheduleBlock(
                                course_subject_id=course_subject.id,
                                weekday=weekday,
                                start_time=start,
                                end_time=end,
                                room=f"Sala {course_index + 1}",
                            )
                        )
                        teacher_busy.add(teacher_key)
                        course_busy.add(course_key)
                        schedule_count += 1
                        break
        db.flush()

        students = []
        for i in range(24):
            guardian = Guardian(
                rut=make_rut(8_000_000 + i * 91_003),
                first_name=random.choice(FIRST), last_name=random.choice(LAST),
                phone=f"+56 9 {random.randint(1000, 9999)} {random.randint(1000, 9999)}",
            )
            db.add(guardian)
            db.flush()
            course = courses[i % len(courses)]
            student = Student(
                rut=make_rut(22_000_000 + i * 53_011),
                first_name=random.choice(FIRST), last_name=guardian.last_name,
                birth_date=date(2026 - 6 - (i % len(courses)), random.randint(1, 12), random.randint(1, 28)),
                gender=random.choice(["F", "M"]),
                enrollment_date=date(date.today().year, 3, 2),
                course_id=course.id, guardian_id=guardian.id,
            )
            students.append(student)
            db.add(student)
        db.flush()

        # Cobros y pagos: matrícula, mensualidades pagadas, parciales y vencidas.
        fee_count = 0
        payment_count = 0
        for index, student in enumerate(students):
            enrollment_period, enrollment_due = month_period(4)
            fees = [
                Fee(
                    student_id=student.id,
                    concept="matricula",
                    description="Matrícula año escolar",
                    period=enrollment_period,
                    amount=120_000,
                    due_date=enrollment_due,
                )
            ]
            for months_back in (2, 1, 0):
                period, due = month_period(months_back)
                fees.append(
                    Fee(
                        student_id=student.id,
                        concept="mensualidad",
                        description=f"Mensualidad {period}",
                        period=period,
                        amount=65_000,
                        due_date=due,
                    )
                )
            db.add_all(fees)
            db.flush()
            fee_count += len(fees)

            def pay(fee: Fee, amount: int, days_ago: int) -> None:
                nonlocal payment_count
                db.add(
                    Payment(
                        fee_id=fee.id,
                        amount=amount,
                        paid_on=date.today() - timedelta(days=days_ago),
                        method="transferencia",
                        reference=f"TRX-{fee.id:05d}",
                    )
                )
                payment_count += 1

            pay(fees[0], fees[0].amount, 90)  # matrícula pagada
            pay(fees[1], fees[1].amount, 65)  # mes -2 pagado
            if index % 4 == 0:
                pay(fees[2], fees[2].amount, 35)  # mes -1 pagado
                pay(fees[3], fees[3].amount, 5)  # mes actual pagado
            elif index % 4 == 1:
                pay(fees[2], fees[2].amount // 2, 30)  # mes -1 parcial
            elif index % 4 == 2:
                pay(fees[2], fees[2].amount, 30)  # mes -1 pagado, actual pendiente
            # index % 4 == 3: mes -1 vencido y actual pendiente

        # Cuentas de ejemplo para el portal de apoderados y estudiantes.
        first_guardian = students[0].guardian
        db.add_all(
            [
                User(
                    email="apoderado@colegio.cl",
                    full_name=first_guardian.full_name,
                    hashed_password=hash_password("apoderado1234"),
                    role="apoderado",
                    guardian_id=first_guardian.id,
                ),
                User(
                    email="estudiante@colegio.cl",
                    full_name=students[0].full_name,
                    hashed_password=hash_password("estudiante1234"),
                    role="estudiante",
                    student_id=students[0].id,
                ),
            ]
        )

        # Postulaciones de ejemplo, en distintas etapas.
        admission_statuses = ["postulada", "en_revision", "aceptada", "rechazada", "postulada"]
        for i, admission_status in enumerate(admission_statuses):
            guardian_first = random.choice(FIRST)
            guardian_last = random.choice(LAST)
            db.add(
                Admission(
                    applicant_rut=make_rut(25_000_000 + i * 37_009),
                    first_name=random.choice(FIRST),
                    last_name=guardian_last,
                    birth_date=date(2018 - (i % 3), random.randint(1, 12), random.randint(1, 28)),
                    gender=random.choice(["F", "M"]),
                    email=f"postulante{i + 1}@correo.cl",
                    phone=f"+56 9 {random.randint(1000, 9999)} {random.randint(1000, 9999)}",
                    guardian_first_name=guardian_first,
                    guardian_last_name=guardian_last,
                    guardian_rut=make_rut(9_000_000 + i * 61_027),
                    guardian_email=f"apoderado.postulante{i + 1}@correo.cl",
                    guardian_phone=f"+56 9 {random.randint(1000, 9999)} {random.randint(1000, 9999)}",
                    course_id=courses[i % len(courses)].id,
                    year=date.today().year,
                    status=admission_status,
                    application_date=date.today() - timedelta(days=10 - i),
                    notes="Entrevista pendiente" if admission_status == "en_revision" else None,
                )
            )
        db.flush()

        # Asistencia de las últimas semanas (con algunos días sin registro).
        attendance_count = 0
        for day in last_weekdays(15):
            for student in students:
                if random.random() < 0.06:
                    continue  # día sin registro para ese estudiante
                db.add(
                    Attendance(
                        student_id=student.id,
                        course_id=student.course_id,
                        date=day,
                        status=random_status(),
                    )
                )
                attendance_count += 1
        db.flush()

        # Dos evaluaciones por asignatura y curso.
        grade_count = 0
        evaluation_count = 0
        assessments = [
            ("Prueba 1", "prueba", 2, date.today() - timedelta(days=45)),
            ("Trabajo 1", "tarea", 1, date.today() - timedelta(days=20)),
        ]
        evaluations: dict[tuple[int, int], list[Evaluation]] = {}
        for (course_id, subject_id), course_subject in assignments.items():
            evaluations[(course_id, subject_id)] = []
            for title, kind, weight, when in assessments:
                evaluation = Evaluation(
                    course_subject_id=course_subject.id,
                    title=title,
                    kind=kind,
                    weight=weight,
                    date=when,
                )
                db.add(evaluation)
                evaluations[(course_id, subject_id)].append(evaluation)
                evaluation_count += 1
        db.flush()
        by_course: dict[int, list[Student]] = {}
        for student in students:
            by_course.setdefault(student.course_id, []).append(student)
        for course in courses:
            for subject in subjects:
                for student in by_course.get(course.id, []):
                    ability = random.gauss(5.2, 0.9)
                    for evaluation in evaluations[(course.id, subject.id)]:
                        score = round(min(7.0, max(2.0, random.gauss(ability, 0.5))), 1)
                        db.add(
                            Grade(
                                student_id=student.id,
                                subject_id=subject.id,
                                course_id=course.id,
                                title=evaluation.title,
                                score=score,
                                weight=evaluation.weight,
                                date=evaluation.date,
                                evaluation_id=evaluation.id,
                            )
                        )
                        grade_count += 1
        db.commit()
        print(
            "Datos de ejemplo cargados: "
            f"{len(teachers)} profesores, {len(courses)} cursos, {len(subjects)} asignaturas, "
            f"{len(assignments)} asignaturas por curso, {schedule_count} bloques de horario, "
            f"{len(students)} estudiantes, {len(students)} apoderados, "
            f"{len(admission_statuses)} postulaciones, "
            f"{attendance_count} registros de asistencia, {grade_count} notas, "
            f"{evaluation_count} evaluaciones, "
            f"{fee_count} cobros y {payment_count} pagos."
        )
        print("Portal: apoderado@colegio.cl / apoderado1234 · estudiante@colegio.cl / estudiante1234")


if __name__ == "__main__":
    run()
