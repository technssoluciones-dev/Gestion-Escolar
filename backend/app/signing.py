"""Firma electrónica de certificados con HMAC-SHA256.

No reemplaza una firma electrónica avanzada (Ley 19.799), pero permite detectar
alteraciones y verificar la emisión con un código público.
"""
import hashlib
import hmac
import json

from .config import settings


def canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sign(payload: dict) -> str:
    key = (settings.signature_key or settings.secret_key).encode()
    return hmac.new(key, canonical(payload).encode(), hashlib.sha256).hexdigest()


def verify(payload: dict, signature: str) -> bool:
    return hmac.compare_digest(sign(payload), signature or "")


def code_for(signature: str) -> str:
    return f"FE-{signature[:12].upper()}"
