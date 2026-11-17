from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from . import models  # noqa: F401  (registra las tablas)
from .config import settings
from .database import Base, SessionLocal, engine
from .routers import auth, courses, dashboard, guardians, students, teachers
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
                )
            )
            db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    ensure_admin()
    yield


app = FastAPI(title="Sistema de Gestión Escolar", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, dashboard, students, teachers, guardians, courses):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health", tags=["Sistema"])
def health():
    return {"status": "ok"}
