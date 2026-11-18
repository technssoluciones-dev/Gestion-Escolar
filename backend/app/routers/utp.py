"""Módulo UTP: revisión de planificaciones de unidad contra las Bases Curriculares.

Reutiliza el motor `utp_engine.py` (antes control_utp.py) para leer archivos Word,
comparar los OA con las Bases de Lengua y Literatura 7° y 8° y generar el Excel de
control. El resultado se devuelve como JSON y el Excel queda disponible para
descargar durante 24 horas.
"""
import os
import re
import shutil
import tempfile
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from .. import utp_engine as utp
from ..security import require_staff

router = APIRouter(
    prefix="/utp", tags=["UTP"], dependencies=[Depends(require_staff)]
)

BASE_FILE = Path(__file__).resolve().parent.parent / "utp_bases" / "Bases_Curriculares_7_a_8.txt"
def _temp_root() -> Path:
    # tempfile.gettempdir() puede caer en la carpeta del proyecto y algunos equipos
    # no permiten crear carpetas en TEMP, así que se prueba antes de usarla.
    candidates = [
        Path(os.environ[name])
        for name in ("TEMP", "TMP", "TMPDIR")
        if os.environ.get(name) and Path(os.environ[name]).is_absolute()
    ]
    candidates.append(Path(__file__).resolve().parent.parent.parent / "utp-outputs")
    for folder in candidates:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".utp-write-test"
            probe.mkdir()
            probe.rmdir()
            return folder
        except OSError:
            continue
    return Path.cwd()


WORK_DIR = _temp_root() / "gestion-escolar-utp"
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 60 * 1024 * 1024
EXCEL_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SUFFIXES = {".docx", ".txt", ".pdf", ".xlsx"}


def _cleanup() -> None:
    if not WORK_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(hours=24)
    for path in WORK_DIR.glob("*.xlsx"):
        try:
            if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                path.unlink()
        except OSError:
            pass


def _safe_name(name: str, allowed: set[str]) -> str:
    base = Path(name or "archivo").name
    suffix = Path(base).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            422, f"«{base}» no es un archivo válido ({', '.join(sorted(allowed))})"
        )
    return base


def _fecha(value: date | None) -> str | None:
    return value.isoformat() if value else None


@router.get("/bases")
def bases_info():
    """Bases curriculares incluidas en el sistema."""
    return {
        "file": BASE_FILE.name,
        "loaded": BASE_FILE.exists(),
        "size": BASE_FILE.stat().st_size if BASE_FILE.exists() else 0,
        "engine_version": utp.VERSION,
        "description": "Bases Curriculares de Lengua y Literatura 7° y 8° básico",
    }


@router.post("/analyze")
async def analyze(
    planificaciones: list[UploadFile] = File(...),
    bases: UploadFile | None = File(None),
    previo: UploadFile | None = File(None),
    anio: int = Form(date.today().year),
    fecha_revision: date | None = Form(None),
):
    if not 2000 <= anio <= 2100:
        raise HTTPException(422, "El año debe estar entre 2000 y 2100")
    files = [f for f in planificaciones if f and f.filename]
    if not files:
        raise HTTPException(422, "Sube al menos una planificación en Word (.docx)")

    hoy = fecha_revision or date.today()
    _cleanup()
    avisos: list[str] = []
    total = 0

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=WORK_DIR) as tmp_name:
        tmp = Path(tmp_name)

        # Bases: las del sistema o las que sube el usuario
        if bases and bases.filename:
            base_name = _safe_name(bases.filename, {".txt", ".pdf"})
            base_bytes = await bases.read()
            if not base_bytes:
                raise HTTPException(422, "El archivo de Bases está vacío")
            if len(base_bytes) > MAX_FILE_BYTES:
                raise HTTPException(422, "El archivo de Bases supera 20 MB")
            base_path = tmp / f"bases{Path(base_name).suffix.lower()}"
            base_path.write_bytes(base_bytes)
            base_label = base_name
        elif BASE_FILE.exists():
            base_path = BASE_FILE
            base_label = BASE_FILE.name
        else:
            base_path = None
            base_label = ""
            avisos.append(
                "No hay Bases cargadas: se revisan solo fechas, clases y evaluaciones."
            )

        base_oa, comp, oat_bases = {}, None, []
        if base_path is not None:
            try:
                lineas = utp.leer_texto_bases(base_path)
                base_oa = utp.extraer_oa_lengua(lineas)
                oat_bases = utp.extraer_oat(lineas)
            except SystemExit as exc:
                raise HTTPException(422, str(exc)) from exc
            except Exception as exc:
                raise HTTPException(
                    422, f"No se pudieron leer las Bases curriculares: {exc}"
                ) from exc
            if not base_oa:
                avisos.append(
                    "No se ubicaron los OA de Lengua y Literatura 7° y 8° en las "
                    "Bases: se revisan solo fechas, clases y evaluaciones."
                )
            else:
                comp = utp.Comparador(base_oa)

        # Planificaciones
        planes = []
        for upload in files:
            name = _safe_name(upload.filename, {".docx"})
            data = await upload.read()
            if not data:
                avisos.append(f"{name}: el archivo está vacío.")
                continue
            if len(data) > MAX_FILE_BYTES:
                raise HTTPException(422, f"«{name}» supera 20 MB")
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise HTTPException(422, "Los archivos superan 60 MB en total")
            path = tmp / name
            path.write_bytes(data)
            try:
                encontrados = utp.leer_planificaciones(path, anio)
            except Exception as exc:
                avisos.append(f"{name}: no se pudo leer ({exc}).")
                continue
            if not encontrados:
                avisos.append(f"{name}: no se encontró una tabla de planificación.")
            planes += encontrados

        if not planes:
            detalle = " ".join(avisos) or "No se pudo leer ninguna planificación."
            raise HTTPException(422, f"No se pudo analizar ninguna planificación. {detalle}")

        resultados = []
        for plan in planes:
            es_lengua = "lengua" in utp.norm(plan.asignatura)
            if base_oa and es_lengua:
                resultados.append(utp.analizar(plan, base_oa, comp, oat_bases))
            else:
                if base_oa and not es_lengua:
                    avisos.append(
                        f"{plan.docente or plan.archivo}: «{plan.asignatura}» no es Lengua; "
                        "se revisan solo fechas, clases y evaluaciones (sin comparar OA)."
                    )
                resultados.append(utp.analizar(plan, {}, None, oat_bases))

        # Excel de control, conservando las anotaciones de un control anterior
        salida = tmp / "Control_UTP.xlsx"
        if previo and previo.filename:
            previo_name = _safe_name(previo.filename, {".xlsx"})
            previo_bytes = await previo.read()
            if len(previo_bytes) > MAX_FILE_BYTES:
                raise HTTPException(422, "El Excel anterior supera 20 MB")
            if previo_bytes:
                salida.write_bytes(previo_bytes)
        try:
            manual = utp.leer_manual(salida)
        except Exception:
            salida.unlink(missing_ok=True)
            manual = {"control": {}, "clases": {}, "evals": {}}
            avisos.append(
                "No se pudo leer el Excel anterior: se generó el control sin anotaciones."
            )
        resumen = utp.escribir_excel(planes, resultados, salida, hoy, manual)

        analysis_id = uuid.uuid4().hex
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(salida, WORK_DIR / f"{analysis_id}.xlsx")

    filas, clases, evaluaciones, basales, oats = [], [], [], [], []
    for (plan, estado, semaforo, n_alertas), resultado in zip(resumen, resultados):
        etiqueta = f"{plan.docente or plan.archivo} · {plan.unidad}"
        filas.append(
            {
                "docente": plan.docente,
                "archivo": plan.archivo,
                "asignatura": plan.asignatura,
                "curso": plan.curso,
                "unidad": plan.unidad,
                "inicio": _fecha(plan.inicio) or plan.inicio_txt,
                "cierre": _fecha(plan.cierre) or plan.cierre_txt,
                "estado": estado,
                "clases": len(plan.clases),
                "evaluaciones": len(plan.evaluaciones),
                "alertas": n_alertas,
                "semaforo": semaforo,
                "detalle_alertas": resultado["alertas"],
                "etiqueta": etiqueta,
            }
        )
        for item in resultado["clases"]:
            clase = item["clase"]
            clases.append(
                {
                    "planificacion": etiqueta,
                    "n": clase.n,
                    "oa_citado": clase.oa_txt,
                    "objetivo": clase.objetivo,
                    "revision": item["estado"],
                    "oa_sugerido": item["sugerido"] or item["mejor"],
                    "en_basales": item["en_basales"],
                }
            )
        for item in resultado["evals"]:
            evaluacion = item["eval"]
            evaluaciones.append(
                {
                    "planificacion": etiqueta,
                    "n": evaluacion.n,
                    "tipo": evaluacion.tipo,
                    "oa_citado": evaluacion.oa_txt,
                    "instrumento": evaluacion.instrumento,
                    "procedimiento": evaluacion.procedimiento,
                    "revision": item["estado"],
                    "oa_sugerido": item["sugerido"] or item["mejor"],
                    "trabajado": item["trabajado"],
                }
            )
        for item in resultado["oat"]:
            oats.append(
                {
                    "planificacion": etiqueta,
                    "oat": f"OAT{item['n']}",
                    "dimension": item["dimension"],
                    "texto": item["texto"],
                    "relacion": item["relacion"],
                    "estado": item["estado"],
                }
            )
        for item in resultado["basales"]:
            basales.append(
                {
                    "planificacion": etiqueta,
                    "oa": f"OA{item['oa']}",
                    "oficial": item["oficial"],
                    "clases": item["n_clases"],
                    "evaluaciones": item["n_evals"],
                    "estado": item["estado"],
                }
            )

    return {
        "analysis_id": analysis_id,
        "download_url": f"/utp/analyses/{analysis_id}/excel",
        "engine_version": utp.VERSION,
        "anio": anio,
        "fecha_revision": hoy.isoformat(),
        "bases": {
            "nombre": base_label,
            "oa": {str(nivel): len(items) for nivel, items in base_oa.items()},
        },
        "resumen": filas,
        "clases": clases,
        "evaluaciones": evaluaciones,
        "basales": basales,
        "oat": oats,
        "avisos": avisos,
    }


@router.get("/analyses/{analysis_id}/excel")
def download_excel(analysis_id: str):
    if not re.fullmatch(r"[0-9a-f]{32}", analysis_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análisis no encontrado")
    path = WORK_DIR / f"{analysis_id}.xlsx"
    if not path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "El Excel ya no está disponible; vuelve a analizar las planificaciones",
        )
    return FileResponse(
        path,
        media_type=EXCEL_TYPE,
        filename="Control_UTP.xlsx",
    )
