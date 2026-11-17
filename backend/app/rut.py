"""Validación del RUT chileno (módulo 11)."""
import re


def calc_dv(body: str) -> str:
    total, factor = 0, 2
    for digit in reversed(body):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    result = 11 - (total % 11)
    if result == 11:
        return "0"
    if result == 10:
        return "K"
    return str(result)


def normalize_rut(value: str) -> str:
    """Acepta '12.345.678-5', '12345678-5' o '123456785'. Devuelve '12345678-5'."""
    clean = re.sub(r"[^0-9kK]", "", value or "").upper()
    if len(clean) < 7 or not clean[:-1].isdigit() or len(clean[:-1]) > 8:
        raise ValueError("RUT inválido")
    body, dv = clean[:-1], clean[-1]
    if calc_dv(body) != dv:
        raise ValueError("RUT inválido: el dígito verificador no corresponde")
    return f"{int(body)}-{dv}"


def format_rut(rut: str) -> str:
    """'12345678-5' -> '12.345.678-5'."""
    body, dv = rut.split("-")
    return f"{int(body):,}".replace(",", ".") + "-" + dv
