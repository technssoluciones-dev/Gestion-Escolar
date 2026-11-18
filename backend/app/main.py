from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, select, text

from . import models  # noqa: F401  (registra las tablas)
from .config import settings
from .database import Base, SessionLocal, engine
from .routers import (
    admissions,
    attendance,
    auth,
    courses,
    dashboard,
    evaluations,
    fees,
    grades,
    guardians,
    notifications,
    payments,
    portal,
    public,
    reports,
    schedules,
    students,
    subjects,
    teachers,
    users,
    utp,
)
from .security import hash_password


def ensure_admin() -> None:
    """Crea el usuario administrador la primera vez que se inicia el sistema."""
    with SessionLocal() as db:
        if db.scalar(select(models.User).limit(1)) is None:
            db.add(
                models.User(
                    email=settings.admin_email.lower(),
                    full_name="Administrador",
                    hashed_password=hash_password(settings.admin_password),
                    role="admin",
                )
            )
            db.commit()


def ensure_schema() -> None:
    """Agrega columnas nuevas a bases de datos creadas con versiones anteriores."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    statements = []
    if "role" not in columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'admin'"
        )
    if "guardian_id" not in columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN guardian_id INTEGER REFERENCES guardians(id)"
        )
    if "student_id" not in columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN student_id INTEGER REFERENCES students(id)"
        )
    if "teacher_id" not in columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN teacher_id INTEGER REFERENCES teachers(id)"
        )
    if "grades" in inspector.get_table_names():
        grade_columns = {column["name"] for column in inspector.get_columns("grades")}
        if "evaluation_id" not in grade_columns:
            statements.append(
                "ALTER TABLE grades ADD COLUMN evaluation_id INTEGER REFERENCES evaluations(id)"
            )
    if "admissions" in inspector.get_table_names():
        admission_columns = {
            column["name"] for column in inspector.get_columns("admissions")
        }
        if "access_token" not in admission_columns:
            statements.append(
                "ALTER TABLE admissions ADD COLUMN access_token VARCHAR(64)"
            )
    if "payment_intents" in inspector.get_table_names():
        intent_columns = {
            column["name"] for column in inspector.get_columns("payment_intents")
        }
        if "gateway_token" not in intent_columns:
            statements.append(
                "ALTER TABLE payment_intents ADD COLUMN gateway_token VARCHAR(128)"
            )
        if "gateway_url" not in intent_columns:
            statements.append(
                "ALTER TABLE payment_intents ADD COLUMN gateway_url VARCHAR(255)"
            )
    if statements:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    ensure_schema()
    ensure_admin()
    yield


app = FastAPI(title="Sistema de Gestión Escolar", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

for module in (
    auth,
    dashboard,
    students,
    teachers,
    guardians,
    courses,
    subjects,
    attendance,
    grades,
    evaluations,
    admissions,
    fees,
    users,
    notifications,
    payments,
    portal,
    public,
    reports,
    utp,
):
    app.include_router(module.router, prefix="/api")

app.include_router(admissions.documents_router, prefix="/api")
app.include_router(admissions.interviews_router, prefix="/api")
app.include_router(admissions.scores_router, prefix="/api")
app.include_router(schedules.course_subject_router, prefix="/api")
app.include_router(schedules.schedule_router, prefix="/api")


@app.get("/api/health", tags=["Sistema"])
def health():
    return {"status": "ok"}
