"""Cliente mínimo de Webpay Plus (Transbank REST).

Crear la transacción devuelve `token` y `url`; la familia es redirigida a esa
URL con `token_ws` y Transbank vuelve a `return_url` con el mismo token. El
commit confirma el cobro. Sin WEBPAY_COMMERCE_CODE/WEBPAY_API_KEY el sistema
usa el checkout simulado.
"""
import httpx

from .config import settings

INTEGRATION_URL = "https://webpay3gint.transbank.cl"
PRODUCTION_URL = "https://webpay3g.transbank.cl"
API_PATH = "/rswebpaytransaction/api/webpay/v1.2/transactions"
TIMEOUT = 20


class WebpayNotConfigured(RuntimeError):
    pass


class WebpayError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.webpay_commerce_code and settings.webpay_api_key)


def _base_url() -> str:
    if settings.webpay_environment == "production":
        return PRODUCTION_URL
    return INTEGRATION_URL


def _headers() -> dict[str, str]:
    if not is_configured():
        raise WebpayNotConfigured(
            "Webpay no está configurado (WEBPAY_COMMERCE_CODE y WEBPAY_API_KEY)"
        )
    return {
        "Tbk-Api-Key-Id": settings.webpay_commerce_code,
        "Tbk-Api-Key-Secret": settings.webpay_api_key,
        "Content-Type": "application/json",
    }


def create_transaction(
    buy_order: str, session_id: str, amount: int, return_url: str
) -> dict:
    try:
        response = httpx.post(
            f"{_base_url()}{API_PATH}",
            headers=_headers(),
            json={
                "buy_order": buy_order,
                "session_id": session_id,
                "amount": amount,
                "return_url": return_url,
            },
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise WebpayError(f"No se pudo conectar con Webpay: {exc}") from exc
    if response.status_code >= 400:
        raise WebpayError(f"Webpay rechazó la transacción (HTTP {response.status_code})")
    return response.json()


def commit_transaction(token: str) -> dict:
    try:
        response = httpx.put(
            f"{_base_url()}{API_PATH}/{token}",
            headers=_headers(),
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise WebpayError(f"No se pudo conectar con Webpay: {exc}") from exc
    if response.status_code >= 400:
        raise WebpayError(f"Webpay no confirmó el pago (HTTP {response.status_code})")
    return response.json()
