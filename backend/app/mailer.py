"""Envío de correos por SMTP. Configurable con variables de entorno."""
import smtplib
from email.message import EmailMessage

from .config import settings


class EmailNotConfigured(RuntimeError):
    pass


def send_email(to: str, subject: str, body: str) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        raise EmailNotConfigured(
            "El envío de correos no está configurado (SMTP_HOST y SMTP_FROM)"
        )
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    smtp_class = smtplib.SMTP_SSL if settings.smtp_ssl else smtplib.SMTP
    with smtp_class(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        if settings.smtp_tls and not settings.smtp_ssl:
            server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)
