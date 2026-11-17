"""Configuración del sistema. Todo se puede cambiar con variables de entorno."""
import os


class Settings:
    # Por defecto usa SQLite (un archivo). Para PostgreSQL:
    # DATABASE_URL=postgresql+psycopg://usuario:clave@localhost/colegio
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./colegio.db")
    secret_key: str = os.getenv("SECRET_KEY", "cambia-esta-clave-larga-en-produccion-32-bytes")
    token_minutes: int = int(os.getenv("TOKEN_MINUTES", "480"))
    admin_email: str = os.getenv("ADMIN_EMAIL", "admin@colegio.cl")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "admin1234")
    cors_origins: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")


settings = Settings()
