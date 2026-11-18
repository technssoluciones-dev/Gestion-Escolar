"""Envío de mensajes por WhatsApp Cloud API (Meta)."""
import re

import httpx

from .config import settings


class WhatsAppNotConfigured(RuntimeError):
    pass


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 9 and digits.startswith("9"):
        digits = "56" + digits
    if not 10 <= len(digits) <= 15:
        raise ValueError(
            "El teléfono del apoderado debe incluir el código de país"
        )
    return digits


def send_whatsapp(phone: str, text: str) -> None:
    if not settings.whatsapp_token or not settings.whatsapp_phone_id:
        raise WhatsAppNotConfigured(
            "El envío por WhatsApp no está configurado "
            "(WHATSAPP_TOKEN y WHATSAPP_PHONE_ID)"
        )
    response = httpx.post(
        f"{settings.whatsapp_api_url}/{settings.whatsapp_phone_id}/messages",
        headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
        json={
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": text},
        },
        timeout=15,
    )
    response.raise_for_status()
