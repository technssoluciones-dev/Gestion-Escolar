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

    # Correo saliente (opcional). Sin SMTP_HOST el envío queda deshabilitado.
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")
    smtp_tls: bool = os.getenv("SMTP_TLS", "1") != "0"
    smtp_ssl: bool = os.getenv("SMTP_SSL", "0") == "1"


    # WhatsApp Cloud API (opcional). Sin WHATSAPP_TOKEN/PHONE_ID queda deshabilitado.
    whatsapp_token: str = os.getenv("WHATSAPP_TOKEN", "")
    whatsapp_phone_id: str = os.getenv("WHATSAPP_PHONE_ID", "")
    whatsapp_api_url: str = os.getenv(
        "WHATSAPP_API_URL", "https://graph.facebook.com/v20.0"
    )

    # Webpay Plus (Transbank). Sin estas variables el checkout usa el modo simulado.
    webpay_commerce_code: str = os.getenv("WEBPAY_COMMERCE_CODE", "")
    webpay_api_key: str = os.getenv("WEBPAY_API_KEY", "")
    webpay_environment: str = os.getenv("WEBPAY_ENVIRONMENT", "integration")
    public_api_url: str = os.getenv("PUBLIC_API_URL", "http://localhost:8000/api")
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # Firma electrónica de certificados (HMAC-SHA256). Usa SECRET_KEY si está vacía.
    signature_key: str = os.getenv("SIGNATURE_KEY", "")

settings = Settings()

