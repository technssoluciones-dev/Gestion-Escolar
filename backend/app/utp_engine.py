#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
control_utp.py  -  Control de planificaciones para UTP
=======================================================

Lee la(s) planificacion(es) de unidad en Word (.docx), las compara con las
Bases Curriculares (txt o pdf) y entrega un Excel de control muy simple:

  * CONTROL      -> 1 fila por docente y unidad, con semaforo (la hoja que mira UTP)
  * CLASES       -> cada clase planificada, el OA que cita y si calza con las Bases
  * EVALUACIONES -> cada evaluacion de la unidad y si su OA calza con las Bases
  * OA BASALES   -> cada OA declarado y cuantas clases / evaluaciones lo trabajan
  * LEEME        -> como leer y llenar el control

Uso rapido (terminal):

    python control_utp.py PLANIFICACION.docx --bases BASES.txt

    # varias planificaciones (archivos o una carpeta completa):
    python control_utp.py carpeta_planificaciones/ --bases BASES.txt --salida Control_UTP.xlsx

Si el Excel de salida ya existe, lo que UTP escribio a mano (clase creada,
fechas, observaciones) se conserva al volver a ejecutar el script.

Instalacion (una sola vez):   pip install python-docx xlsxwriter openpyxl
"""
import argparse
import difflib
import math
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import docx
import xlsxwriter
from openpyxl import load_workbook

VERSION = "2026-11-14-d (tipeo + ejes + OAT)"


# --------------------------------------------------------------------------
# Utilidades de texto
# --------------------------------------------------------------------------

def norm(s):
    """minusculas y sin tildes (para comparar)."""
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def limpia(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


STOP = set("""
de la el los las un una unos unas y o u e en con por para sobre del al lo le les se su sus que como mas muy
ya es son ser fue han hay este esta estos estas ese esa eso entre desde hasta segun sin tambien cada
cuando donde cual cuales quien otros otras otro otra ellos ellas ello asi todo toda todos todas
sea sean tal tales ante bajo tras mediante durante pertinente considerando segun puede pueden
estudiantes estudiante clase clases unidad
""".split())


# Equivalencias de vocabulario (raiz de 5 letras -> concepto). Se pueden ampliar a gusto:
# sirven para que, por ejemplo, "texto argumentativo" y "persuadir" cuenten como lo mismo.
SINONIMOS = {
    "persu": "argum", "critic": "argum",
    "expos": "audie", "expon": "audie", "orale": "audie", "oral": "audie",
    "colo": "dialo", "coloq": "dialo", "debat": "dialo",
    "lectu": "leer", "domic": "leer",
}


def stems(texto):
    out = []
    for t in re.findall(r"[a-z]{3,}", norm(texto)):
        if t in STOP:
            continue
        r = t[:5]
        out.append(SINONIMOS.get(r, r))
    return out


# --------------------------------------------------------------------------
# Bases curriculares (Lengua y Literatura 7 y 8 basico)
# --------------------------------------------------------------------------

@dataclass
class OA:
    nivel: int
    num: int
    texto: str          # texto completo (con vinetas)
    corto: str          # enunciado principal
    eje: str


NIVELES_TXT = {7: "7°", 8: "8°"}

RUIDO = [
    r"^\d+\s+Bases Curriculares", r"^Bases Curriculares 2015", r"^\d+$", r"^\d\s+Véase el anexo",
    r"^(Lectura|Escritura|Comunicación oral|Investigación|sobre lengua y|literatura|"
    r"Objetivos de Aprendizaje|Octavo|básico|Primero|medio|Séptimo básico)$",
    r"^Se espera que los y las estudiantes sean capaces de",
]
RUIDO_RE = [re.compile(p) for p in RUIDO]
INICIO_ESCRITURA = norm("Expresarse en forma creativa por medio de la escritura")
INICIO_ORAL = norm("Comprender, comparar y evaluar textos orales")
INICIO_INVEST = norm("Realizar investigaciones")


def leer_texto_bases(ruta):
    ruta = Path(ruta)
    if not ruta.exists():
        cerca = sorted(p.name for p in Path(".").iterdir()
                       if p.suffix.lower() in (".pdf", ".txt", ".docx") and not p.name.startswith("~$"))
        msg = f"ERROR: no encuentro el archivo de bases: {ruta}\n"
        if cerca:
            msg += "Archivos PDF/TXT/DOCX que hay en esta carpeta:\n" + "\n".join(f"  - {n}" for n in cerca)
        else:
            msg += "No hay archivos PDF/TXT/DOCX en esta carpeta; use la ruta completa entre comillas."
        sys.exit(msg)
    if ruta.suffix.lower() == ".pdf":
        if shutil.which("pdftotext"):
            res = subprocess.run(["pdftotext", str(ruta), "-"], capture_output=True, text=True, encoding="utf-8")
            return res.stdout.splitlines()
        try:
            from pypdf import PdfReader  # pip install pypdf
        except ImportError:
            sys.exit("ERROR: para leer el PDF de las bases instale pypdf:  pip install pypdf")
        print("  (leyendo el PDF con pypdf; puede tardar un poco)")
        paginas = [(pg.extract_text() or "") for pg in PdfReader(str(ruta)).pages]
        return "\n".join(paginas).splitlines()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return ruta.read_text(encoding=enc).splitlines()
        except UnicodeDecodeError:
            continue
    sys.exit("ERROR: no pude leer el archivo de bases (codificacion desconocida).")


def _parse_seccion(lineas, nivel):
    oas, actual, esperado, eje = {}, None, 1, "Lectura"
    for raw in lineas:
        ln = raw.strip().replace("\t", " ")
        if not ln or any(r.match(ln) for r in RUIDO_RE):
            continue
        m = re.match(r"^(\d{1,2})\.\s+(\S.*)$", ln)
        if m and int(m.group(1)) == esperado:
            if actual:
                oas[actual["num"]] = actual
            esperado += 1
            txt = m.group(2)
            n = norm(txt)
            if n.startswith(INICIO_ESCRITURA):
                eje = "Escritura"
            elif n.startswith(INICIO_ORAL):
                eje = "Comunicación oral"
            elif n.startswith(INICIO_INVEST):
                eje = "Investigación"
            actual = {"num": int(m.group(1)), "partes": [txt], "eje": eje}
        elif actual:
            actual["partes"].append(ln.lstrip("•").strip() if ln.startswith("•") else ln)
    if actual:
        oas[actual["num"]] = actual
    resultado = {}
    for num, d in oas.items():
        texto = limpia(" ".join(d["partes"]))
        texto = re.sub(r"(cada uno)\d\.", r"\1.", texto)
        corto = re.split(r"[:•]", texto)[0].strip().rstrip(",;")
        resultado[num] = OA(nivel, num, texto, corto, d["eje"])
    return resultado


def extraer_oa_lengua(lineas):
    """Devuelve {7: {num: OA}, 8: {num: OA}} de Lengua y Literatura."""
    i7 = None
    for i, ln in enumerate(lineas):
        if ln.strip() == "Séptimo básico":
            ventana = "\n".join(lineas[i:i + 80])
            if "Leer habitualmente para aprender y recrearse" in ventana:
                i7 = i
                break
    if i7 is None:
        return {}
    i8 = next((i for i in range(i7 + 1, len(lineas)) if lineas[i].strip() == "Octavo"), None)
    if i8 is None:
        return {}
    ifin = next((i for i in range(i8 + 1, len(lineas)) if lineas[i].strip() == "Primero"), len(lineas))
    return {7: _parse_seccion(lineas[i7:i8], 7), 8: _parse_seccion(lineas[i8:ifin], 8)}


# --------------------------------------------------------------------------
# Objetivos de Aprendizaje Transversales (OAT)
# --------------------------------------------------------------------------
# Las Bases los listan por dimension pero SIN numerarlos. Se numeran en el orden en que
# aparecen (OAT1 = primer objetivo de la dimension fisica ... OAT34 = ultimo de TIC).

DIMENSIONES_OAT = [
    ("dimension fisica", "Dimensión física"),
    ("dimension afectiva", "Dimensión afectiva"),
    ("dimension cognitiva", "Dimensión cognitiva-intelectual"),
    ("dimension sociocultural", "Dimensión sociocultural y ciudadana"),
    ("dimension moral", "Dimensión moral"),
    ("dimension espiritual", "Dimensión espiritual"),
    ("proactividad y trabajo", "Proactividad y trabajo"),
    ("planes y proyectos personales", "Planes y proyectos personales"),
    ("tecnologias de la informacion", "Tecnologías de la información y la comunicación (TIC)"),
]
_RUIDO_PAG = re.compile(r"^\d+\s*$|bases curriculares", re.I)


def extraer_oat(lineas):
    """-> lista de dicts {n, dimension, texto}; [] si no encuentra la seccion."""
    ini = next((i for i, l in enumerate(lineas) if norm(l).strip() == "dimension fisica"), None)
    if ini is None:
        return []
    out, dim, cur = [], None, None
    for l in lineas[ini:]:
        t = l.strip()
        nt = norm(t).strip()
        if nt.startswith("referencias"):
            break
        cab = next((nombre for clave, nombre in DIMENSIONES_OAT
                    if nt == clave or (nt.startswith(clave) and len(nt) <= 50)), None)
        if cab:
            dim, cur = cab, None
            continue
        if t.startswith("•"):
            cur = {"n": len(out) + 1, "dimension": dim or "", "texto": limpia(t.lstrip("•\t "))}
            out.append(cur)
        elif cur is not None and t and not _RUIDO_PAG.search(t):
            cur["texto"] = limpia(cur["texto"] + " " + t)
    return out


def relacionar_oat(oat_bases, textos, umbral=0.12, maximo=4):
    """Pista: para cada OAT, que clases/evaluaciones hablan de algo parecido (por palabras).
    textos: lista de (etiqueta, texto). -> {n_oat: [(etiqueta, puntaje), ...]}"""
    docs = {o["n"]: stems(o["texto"]) for o in oat_bases}
    N = len(docs) or 1
    df = Counter()
    for toks in docs.values():
        df.update(set(toks))
    idf = {t: math.log((N + 1) / (c + 1)) + 1 for t, c in df.items()}

    def vec(toks):
        tf = Counter(toks)
        v = {t: c * idf.get(t, 1.0) for t, c in tf.items()}
        nrm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / nrm for t, x in v.items()}

    vo = {n: vec(t) for n, t in docs.items()}
    vt = [(et, vec(stems(tx))) for et, tx in textos]
    res = {}
    for n, v in vo.items():
        sc = sorted(((sum(x * b.get(t, 0.0) for t, x in v.items()), et) for et, b in vt), reverse=True)
        res[n] = [(et, round(s, 2)) for s, et in sc[:maximo] if s >= umbral]
    return res


# Verbos que delatan de que eje habla un objetivo (se usa solo si hay UN eje claro)
EJE_PATRONES = {
    "Escritura": re.compile(r"\b(escrib\w*|elabor\w*|redact\w*|produccion textual)"),
    "Lectura": re.compile(r"\b(leer|lee\w*|lectur\w*|comprend\w*|analiz\w*|interpret\w*)"),
    "Comunicación oral": re.compile(r"\b(oralmente|expon\w*|exposicion\w*|dialog\w*|debat\w*|coloqui\w*)"),
    "Investigación": re.compile(r"\b(investig\w*|recopil\w*)"),
}


def ejes_en(texto):
    t = norm(texto)
    return {eje for eje, rx in EJE_PATRONES.items() if rx.search(t)}


class Comparador:
    """Compara el texto de una clase/evaluacion con los OA oficiales (similitud de palabras)."""
    # Un OA "coincide" si su parecido con el texto es al menos RELATIVO veces el del OA mas parecido
    # (y no es casi nulo). Es una ayuda de orden, no un veredicto.
    RELATIVO = 0.5
    MINIMO = 0.08
    PESO_ENUNCIADO = 2
    # Si el objetivo menciona UN solo eje (escribir, leer, exponer, investigar), solo se comparan
    # los OA de ese eje: citar un OA de lectura para una clase de escritura es una alerta clara.
    SOLO_EJE = True
    CORTE_TIPEO = 0.8     # parecido minimo para corregir una palabra mal escrita

    def __init__(self, bases):
        self.bases = bases
        docs = [(n, k, stems(oa.texto) + stems(oa.corto) * self.PESO_ENUNCIADO)
                for n, d in bases.items() for k, oa in d.items()]
        N = len(docs) or 1
        df = Counter()
        for _, _, toks in docs:
            df.update(set(toks))
        self.idf = {t: math.log((N + 1) / (c + 1)) + 1 for t, c in df.items()}
        self.vec = {(n, k): self._vec(toks) for n, k, toks in docs}
        self.vocab = list(self.idf)
        self._cache_tipeo = {}

    def _vec(self, toks):
        tf = Counter(toks)
        v = {t: c * self.idf.get(t, 1.0) for t, c in tf.items()}
        nrm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / nrm for t, x in v.items()}

    def _corrige(self, toks):
        """Cambia las raices que no existen en las Bases por la mas parecida (errores de tipeo)."""
        out = []
        for t in toks:
            if t in self.idf or len(t) < 5:
                out.append(t)
                continue
            if t not in self._cache_tipeo:
                cerca = difflib.get_close_matches(t, self.vocab, n=1, cutoff=self.CORTE_TIPEO)
                self._cache_tipeo[t] = cerca[0] if cerca else t
            out.append(self._cache_tipeo[t])
        return out

    def _coseno(self, a, b):
        if len(a) > len(b):
            a, b = b, a
        return sum(x * b.get(t, 0.0) for t, x in a.items())

    def evaluar(self, texto, oas, niveles):
        """-> (estado, mejor_oa_texto, sugerido_texto, existe)

        Se evalua CADA nivel por separado (7° y 8° numeran distinto los OA).
        Estados: Coincide (calza en todos los niveles de la planificacion),
        Parcial (calza solo en algunos), Revisar, OA no existe, Sin OA, Sin texto.
        """
        niveles = [n for n in niveles if n in self.bases]
        q = self._vec(self._corrige(stems(texto)))
        ejes = ejes_en(texto)
        eje = next(iter(ejes)) if len(ejes) == 1 else None
        ranking, sugeridos = {}, []
        for n in niveles:
            sc = sorted(((self._coseno(q, self.vec[(n, k)]) * (0.0 if (self.SOLO_EJE and eje and self.bases[n][k].eje != eje) else 1.0), k)
                         for k in self.bases[n]), reverse=True)
            ranking[n] = {k: (s, i + 1) for i, (s, k) in enumerate(sc)}
            if sc:
                sugeridos.append(f"{NIVELES_TXT[n]} OA{sc[0][1]}")
        sugerido = " · ".join(sugeridos)
        if not oas:
            return "Sin OA", "", sugerido, False
        mejores, oks, existe = [], [], False
        for n in niveles:
            cand = [(ranking[n][k][0], ranking[n][k][1], k) for k in oas if k in ranking[n]]
            if not cand:
                mejores.append(f"{NIVELES_TXT[n]}: no existe")
                continue
            existe = True
            s, r, k = max(cand)
            tope = max(v[0] for v in ranking[n].values()) or 1.0
            ok = (s >= self.MINIMO and s / tope >= self.RELATIVO) or r == 1
            mejores.append(f"{NIVELES_TXT[n]} OA{k}")
            if ok:
                oks.append(n)
        mejor = " · ".join(mejores)
        if not existe:
            return "OA no existe", "", sugerido, False
        if not stems(texto):
            return "Sin texto", mejor, sugerido, True
        if len(oks) == len(niveles):
            return "Coincide", mejor, sugerido, True
        if oks:
            return "Parcial: solo " + " y ".join(NIVELES_TXT[n] for n in oks), mejor, sugerido, True
        return "Revisar", mejor, sugerido, True


# --------------------------------------------------------------------------
# Planificacion (Word)
# --------------------------------------------------------------------------

@dataclass
class Clase:
    n: int
    oa_txt: str
    oas: list
    objetivo: str


@dataclass
class Evaluacion:
    n: int
    tipo: str
    oa_txt: str
    oas: list
    instrumento: str
    procedimiento: str


@dataclass
class Plan:
    archivo: str
    docente: str = ""
    asignatura: str = ""
    curso: str = ""
    niveles: list = field(default_factory=list)
    unidad: str = ""
    inicio: date = None
    cierre: date = None
    inicio_txt: str = ""
    cierre_txt: str = ""
    n_declaradas: int = None
    basales: list = field(default_factory=list)
    oat: list = field(default_factory=list)
    clases: list = field(default_factory=list)
    evaluaciones: list = field(default_factory=list)
    n_indicadores: int = 0
    alertas_lectura: list = field(default_factory=list)

    @property
    def clave(self):
        return (self.docente, self.asignatura, self.unidad)


MESES = {m: i + 1 for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split())}
MESES["setiembre"] = 9


def parse_fecha(txt, anio):
    t = norm(txt)
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", t)
    if m:
        d, mo, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        a = a + 2000 if a < 100 else a
        try:
            return date(a, mo, d)
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\s*(?:de\s+)?([a-z]+)(?:\s+(?:de\s+)?(\d{4}))?", t)
    if m and m.group(2) in MESES:
        a = int(m.group(3)) if m.group(3) else anio
        try:
            return date(a, MESES[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    return None


def numeros_oa(txt):
    return sorted({int(x) for x in re.findall(r"OA\s*0*(\d+)", txt or "", flags=re.I)})


def numeros_oat(txt):
    return sorted({int(x) for x in re.findall(r"OAT\s*0*(\d+)", txt or "", flags=re.I)})


def celdas_unicas(row):
    vistos, out = set(), []
    for c in row.cells:
        if id(c._tc) in vistos:
            continue
        vistos.add(id(c._tc))
        out.append(c.text.strip())
    return out


def _valor_tras(cells, etiqueta):
    for i, t in enumerate(cells):
        if norm(t).startswith(etiqueta):
            for v in cells[i + 1:]:
                if limpia(v):
                    return limpia(v)
    return ""


def leer_planificaciones(ruta, anio):
    d = docx.Document(str(ruta))
    planes = []
    for tabla in d.tables:
        filas = [celdas_unicas(r) for r in tabla.rows]
        texto_total = " ".join(" ".join(f) for f in filas[:12])
        if "docente" not in norm(texto_total):
            continue
        p = Plan(archivo=Path(ruta).name)
        estado = "cabecera"
        indic = set()
        for cells in filas:
            if not cells:
                continue
            primero = norm(cells[0])
            if estado == "cabecera":
                if primero.startswith("planificacion"):
                    m = re.search(r"unidad\s*(\d+)", norm(cells[0]))
                    if m:
                        p.unidad = f"UNIDAD {m.group(1)}"
                elif primero.startswith("asignatura"):
                    p.asignatura = _valor_tras(cells, "asignatura").upper()
                    p.curso = re.sub(r"^.*?(\d.*)$", r"\1", p.asignatura) if re.search(r"\d", p.asignatura) else ""
                    p.niveles = sorted({int(x) for x in re.findall(r"(\d)\s*[°º]", p.asignatura)})
                    p.asignatura = limpia(re.sub(r"\d.*$", "", p.asignatura))
                    p.curso = limpia(p.curso)
                elif primero.startswith("docente"):
                    p.docente = _valor_tras(cells, "docente")
                elif primero.startswith("nombre de unidad"):
                    v = _valor_tras(cells, "nombre de unidad")
                    if v:
                        p.unidad = v.upper()
                elif primero.startswith("fecha de inicio"):
                    p.inicio_txt = _valor_tras(cells, "fecha de inicio")
                    p.cierre_txt = _valor_tras(cells, "fecha de cierre")
                    p.inicio = parse_fecha(p.inicio_txt, anio)
                    p.cierre = parse_fecha(p.cierre_txt, anio)
                elif primero.startswith("cantidad de clases"):
                    m = re.search(r"\d+", _valor_tras(cells, "cantidad de clases"))
                    p.n_declaradas = int(m.group()) if m else None
                elif primero.startswith("objetivos de aprendizaje transversales"):
                    p.oat = numeros_oat(" ".join(cells[1:]))
                elif primero.startswith("objetivos basales"):
                    p.basales = numeros_oa(" ".join(cells[1:]))
                elif primero.startswith("eje") and "oa" in primero:
                    estado = "clases"
            elif estado == "clases":
                if primero.startswith("estrateg"):
                    estado = "estrategias"
                    continue
                if primero.startswith("ruta"):
                    continue
                obj = cells[1] if len(cells) > 1 else ""
                for c in cells:
                    if norm(c).startswith("indicadores de evaluacion"):
                        indic.update(limpia(x) for x in c.splitlines()[1:] if limpia(x))
                if not limpia(obj) and not numeros_oa(cells[0]):
                    continue
                p.clases.append(Clase(len(p.clases) + 1, limpia(cells[0]), numeros_oa(cells[0]),
                                      limpia(obj.replace("\n", " ; "))))
            elif estado == "estrategias":
                if primero.startswith("tipo de evaluacion"):
                    estado = "evaluaciones"
            elif estado == "evaluaciones":
                if len(cells) >= 3 and any(limpia(c) for c in cells[1:]):
                    tipo = limpia(cells[0])
                    oa_txt = limpia(cells[1])
                    instr = limpia(cells[2])
                    proc = limpia(cells[3]) if len(cells) > 3 else ""
                    p.evaluaciones.append(Evaluacion(len(p.evaluaciones) + 1, tipo, oa_txt, numeros_oa(oa_txt),
                                                     instr, proc))
        p.n_indicadores = len(indic)
        if not p.unidad:
            p.unidad = "(sin nombre de unidad)"
        planes.append(p)
    return planes


# --------------------------------------------------------------------------
# Analisis: plan vs bases
# --------------------------------------------------------------------------

def _rotulo_oas(oas):
    return ", ".join(f"OA{n}" for n in oas) if oas else "—"


def corto_oficial(bases, niveles, oas, maxlen=200):
    partes = []
    for n in oas:
        for niv in niveles:
            oa = bases.get(niv, {}).get(n)
            if oa:
                base_txt = oa.texto if len(oa.corto) < 40 else oa.corto
                t = base_txt if len(base_txt) <= maxlen else base_txt[:maxlen].rsplit(" ", 1)[0] + "…"
                partes.append(f"{NIVELES_TXT[niv]} OA{n}: {t}")
    return "\n".join(partes)


def analizar(plan, bases, comp, oat=None):
    niveles = plan.niveles or sorted(bases)
    res = {"clases": [], "evals": [], "alertas": [], "basales": [], "oat": []}
    usados_clases = set()
    for c in plan.clases:
        estado, mejor, sug, existe = comp.evaluar(c.objetivo, c.oas, niveles) if bases else ("Sin bases", "", "", None)
        usados_clases.update(c.oas)
        en_basales = (all(o in plan.basales for o in c.oas) if c.oas else False)
        res["clases"].append({
            "clase": c, "existe": existe, "en_basales": en_basales, "estado": estado, "mejor": mejor,
            "sugerido": sug if estado.startswith(("Revisar", "Parcial", "OA no existe", "Sin OA")) else "",
            "oficial": corto_oficial(bases, niveles, c.oas) if bases else "",
        })
    usados_eval = set()
    for e in plan.evaluaciones:
        estado, mejor, sug, existe = comp.evaluar(f"{e.instrumento} {e.procedimiento}", e.oas, niveles) \
            if bases else ("Sin bases", "", "", None)
        usados_eval.update(e.oas)
        trabajado = all(o in usados_clases for o in e.oas) if e.oas else False
        res["evals"].append({
            "eval": e, "existe": existe, "trabajado": trabajado, "estado": estado, "mejor": mejor,
            "sugerido": sug if estado.startswith(("Revisar", "Parcial", "OA no existe", "Sin OA")) else "",
        })
    # OA basales
    todos = sorted(set(plan.basales) | usados_clases | usados_eval)
    for k in todos:
        n_cl = sum(1 for c in plan.clases if k in c.oas)
        n_ev = sum(1 for e in plan.evaluaciones if k in e.oas)
        decl = k in plan.basales
        if decl and n_cl == 0:
            est = "⚠ Declarado, sin clases"
        elif not decl:
            est = "⚠ Trabajado pero no declarado en basales"
        else:
            est = "✔ Cubierto"
        res["basales"].append({"oa": k, "n_clases": n_cl, "n_evals": n_ev, "estado": est,
                               "declarado": decl, "oficial": corto_oficial(bases, niveles, [k]) if bases else ""})
    # OAT (Objetivos de Aprendizaje Transversales): son de todas las asignaturas
    if oat:
        por_n = {o["n"]: o for o in oat}
        textos = ([(f"Clase {c.n}", c.objetivo) for c in plan.clases]
                  + [(f"Evaluación {e.n}", f"{e.instrumento} {e.procedimiento}") for e in plan.evaluaciones])
        rel = relacionar_oat(oat, textos)
        for k in plan.oat:
            o = por_n.get(k)
            if o is None:
                res["oat"].append({"n": k, "dimension": "", "texto": "", "relacion": "",
                                   "estado": f"✖ No existe (las Bases traen OAT1 a OAT{len(oat)})"})
                continue
            lig = ", ".join(et for et, _ in rel.get(k, []))
            res["oat"].append({"n": k, "dimension": o["dimension"], "texto": o["texto"], "relacion": lig,
                               "estado": "✔ Con clases relacionadas" if lig else "⚠ Sin clase que se relacione (revisar)"})
    else:
        for k in plan.oat:
            res["oat"].append({"n": k, "dimension": "", "texto": "", "relacion": "", "estado": "— Sin Bases cargadas"})
    # alertas de texto (para la hoja CONTROL)
    A = res["alertas"]
    if plan.inicio is None or plan.cierre is None:
        A.append("Falta o no se entiende la fecha de inicio/cierre")
    elif plan.cierre < plan.inicio:
        A.append("La fecha de cierre es anterior a la de inicio")
    if plan.n_declaradas is not None and plan.n_declaradas != len(plan.clases):
        A.append(f"Declara {plan.n_declaradas} clases y planifica {len(plan.clases)}")
    if not plan.clases:
        A.append("No se encontraron clases en la ruta de aprendizaje")
    sin_clase = [b["oa"] for b in res["basales"] if b["declarado"] and b["n_clases"] == 0]
    if sin_clase:
        A.append("OA declarados sin clase: " + ", ".join(f"OA{k}" for k in sin_clase))
    fuera = [b["oa"] for b in res["basales"] if not b["declarado"] and b["n_clases"] > 0]
    if fuera:
        A.append("OA en clases no declarados en basales: " + ", ".join(f"OA{k}" for k in fuera))
    if not plan.oat:
        A.append("No declara Objetivos de Aprendizaje Transversales (OAT)")
    malos = [b["n"] for b in res["oat"] if b["estado"].startswith("✖")]
    if malos:
        A.append("OAT que no existen en las Bases: " + ", ".join(f"OAT{k}" for k in malos))
    if not bases:
        A.append("Sin Bases cargadas: no se comparó con los OA oficiales")
    rev = [r["clase"].n for r in res["clases"] if r["estado"] not in ("Coincide", "Sin bases")]
    if rev:
        A.append(f"{len(rev)} clase(s) con OA a revisar (clase " + ", ".join(map(str, rev)) + ")")
    if not plan.evaluaciones:
        A.append("Sin evaluaciones planificadas")
    else:
        rev_e = [r["eval"].n for r in res["evals"] if r["estado"] not in ("Coincide", "Sin bases")]
        if rev_e:
            A.append(f"{len(rev_e)} evaluación(es) con OA a revisar (N° " + ", ".join(map(str, rev_e)) + ")")
        no_trab = [r["eval"].n for r in res["evals"] if not r["trabajado"]]
        if no_trab:
            A.append("Evaluación con OA que no se trabaja en las clases (N° " + ", ".join(map(str, no_trab)) + ")")
    if plan.n_indicadores == 0:
        A.append("No incluye indicadores de evaluación")
    return res


# --------------------------------------------------------------------------
# Excel
# --------------------------------------------------------------------------

AZUL = "#1F3864"
AZUL_CLARO = "#D9E2F3"
AMARILLO_UTP = "#FFF8DC"
GRIS = "#F2F2F2"

H_CONTROL = ["Docente", "Asignatura", "Curso", "Unidad", "Inicio", "Cierre", "Estado de la unidad",
             "Avance esperado (por fechas)", "Clases planificadas", "Clases creadas", "Avance real (clases creadas)",
             "Evaluaciones planificadas", "Evaluaciones entregadas", "Alertas contra las Bases", "SEMÁFORO",
             "Observaciones UTP"]
H_CLASES = ["Docente", "Asignatura", "Unidad", "N° clase", "OA que cita el docente", "Objetivo de la clase",
            "¿OA existe en las Bases?", "¿Está en los OA basales?", "Qué dicen las Bases (OA oficial)",
            "Revisión automática", "OA que más se parece", "Fecha de la clase", "¿Clase creada?", "Observación UTP"]
H_EVALS = ["Docente", "Asignatura", "Unidad", "N°", "Tipo", "OA evaluado", "Instrumento", "Procedimiento",
           "¿OA existe en las Bases?", "¿OA se trabaja en las clases?", "Revisión automática", "OA que más se parece",
           "¿Evaluación creada?", "Fecha de entrega", "Observación UTP"]
H_OAT = ["Docente", "Asignatura", "Unidad", "OAT", "Dimensión", "Qué dicen las Bases (OAT oficial)",
         "Clases o evaluaciones que se relacionan (pista)", "Estado"]
H_BASALES = ["Docente", "Asignatura", "Unidad", "OA", "Qué dicen las Bases", "Clases que lo trabajan",
             "Evaluaciones que lo evalúan", "Estado"]


def col(i):
    return xlsxwriter.utility.xl_col_to_name(i)


def leer_manual(ruta):
    """Recupera lo que UTP escribio a mano en un Excel anterior."""
    out = {"control": {}, "clases": {}, "evals": {}}
    ruta = Path(ruta)
    if not ruta.exists():
        return out
    try:
        wb = load_workbook(ruta, data_only=True)
    except Exception as e:  # archivo danado / abierto
        print(f"  (aviso) no pude leer el Excel anterior para conservar tus anotaciones: {e}")
        return out

    def hoja(nombre, claves, manuales, destino, usa_n):
        if nombre not in wb.sheetnames:
            return
        ws = wb[nombre]
        hdr = None
        for r in ws.iter_rows(min_row=1, max_row=15):
            if r[0].value == "Docente":
                hdr = r[0].row
                break
        if hdr is None:
            return
        cab = {c.value: c.column - 1 for c in ws[hdr] if c.value}
        for fila in ws.iter_rows(min_row=hdr + 1, values_only=True):
            if not fila or not fila[0]:
                continue
            key = tuple(str(fila[cab[k]]).strip() for k in claves if k in cab)
            vals = {}
            for m in manuales:
                if m in cab and fila[cab[m]] not in (None, ""):
                    v = fila[cab[m]]
                    vals[m] = v.date() if isinstance(v, datetime) else v
            if vals:
                destino[key] = vals

    hoja("CONTROL", ["Docente", "Asignatura", "Unidad"], ["Observaciones UTP"], out["control"], False)
    hoja("CLASES", ["Docente", "Asignatura", "Unidad", "N° clase"],
         ["Fecha de la clase", "¿Clase creada?", "Observación UTP"], out["clases"], True)
    hoja("EVALUACIONES", ["Docente", "Asignatura", "Unidad", "N°"],
         ["¿Evaluación creada?", "Fecha de entrega", "Observación UTP"], out["evals"], True)
    return out


def semaforo_py(estado, esperado, real, revisadas, evals_plan, evals_ok, alertas):
    if estado == "Sin fecha":
        return "SIN FECHA"
    if revisadas == 0:
        return "POR MARCAR"
    if estado == "Cerrada" and evals_ok < evals_plan:
        return "NO CUMPLE"
    atraso = (esperado or 0) - (real or 0)
    if atraso > 0.2:
        return "NO CUMPLE"
    if atraso > 0.0001 or alertas:
        return "REVISAR"
    return "CUMPLE"


def escribir_excel(planes, resultados, salida, hoy, manual):
    wb = xlsxwriter.Workbook(str(salida))
    wb.set_properties({"title": "Control de planificaciones UTP", "comments": "Generado con control_utp.py"})
    base = {"font_name": "Calibri", "font_size": 11, "valign": "vcenter"}

    def f(**kw):
        d = dict(base)
        d.update(kw)
        return wb.add_format(d)

    titulo = f(bold=True, font_size=18, font_color=AZUL)
    sub = f(font_size=10, font_color="#595959")
    hoy_f = f(bold=True, num_format="dd/mm/yyyy", align="left", font_color=AZUL)
    banda = f(bold=True, font_color="white", bg_color=AZUL, align="center", border=1, border_color="white")
    banda_utp = f(bold=True, font_color="#7F6000", bg_color="#FFE699", align="center", border=1, border_color="white")
    head = f(bold=True, font_color=AZUL, bg_color=AZUL_CLARO, text_wrap=True, align="center", border=1,
             border_color="#BFBFBF")
    head_utp = f(bold=True, font_color="#7F6000", bg_color="#FFE699", text_wrap=True, align="center", border=1,
                 border_color="#BFBFBF")
    txt = f(text_wrap=True, border=1, border_color="#D9D9D9", valign="top")
    txt_c = f(text_wrap=True, border=1, border_color="#D9D9D9", align="center", valign="top")
    txt_b = f(text_wrap=True, border=1, border_color="#D9D9D9", bold=True, valign="top")
    fecha = f(num_format="dd/mm/yyyy", border=1, border_color="#D9D9D9", align="center", valign="top")
    pct = f(num_format="0%", border=1, border_color="#D9D9D9", align="center", valign="top")
    num = f(border=1, border_color="#D9D9D9", align="center", valign="top")
    utp_txt = f(text_wrap=True, border=1, border_color="#D9D9D9", bg_color=AMARILLO_UTP, valign="top")
    utp_c = f(text_wrap=True, border=1, border_color="#D9D9D9", bg_color=AMARILLO_UTP, align="center", valign="top")
    utp_fecha = f(num_format="dd/mm/yyyy", border=1, border_color="#D9D9D9", bg_color=AMARILLO_UTP,
                  align="center", valign="top")
    sem = f(bold=True, align="center", border=1, border_color="#D9D9D9", text_wrap=True)

    verde = wb.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})
    ambar = wb.add_format({"bg_color": "#FFEB9C", "font_color": "#7F6000"})
    rojo = wb.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
    gris = wb.add_format({"bg_color": "#E7E6E6", "font_color": "#595959"})

    def semaforo_cf(ws, rango):
        for t, fm in (("CUMPLE", verde), ("REVISAR", ambar), ("NO CUMPLE", rojo), ("POR MARCAR", gris),
                      ("SIN FECHA", gris)):
            ws.conditional_format(rango, {"type": "cell", "criteria": "==", "value": f'"{t}"', "format": fm})

    def estado_cf(ws, rango):
        ws.conditional_format(rango, {"type": "text", "criteria": "begins with", "value": "✔", "format": verde})
        ws.conditional_format(rango, {"type": "text", "criteria": "begins with", "value": "Coincide", "format": verde})
        ws.conditional_format(rango, {"type": "text", "criteria": "begins with", "value": "⚠", "format": ambar})
        ws.conditional_format(rango, {"type": "text", "criteria": "begins with", "value": "Revisar", "format": ambar})
        ws.conditional_format(rango, {"type": "text", "criteria": "begins with", "value": "Parcial", "format": ambar})
        ws.conditional_format(rango, {"type": "text", "criteria": "begins with", "value": "✖", "format": rojo})
        ws.conditional_format(rango, {"type": "text", "criteria": "begins with", "value": "OA no existe",
                                      "format": rojo})
        ws.conditional_format(rango, {"type": "text", "criteria": "begins with", "value": "Sin OA", "format": rojo})
        ws.conditional_format(rango, {"type": "text", "criteria": "begins with", "value": "Sí", "format": verde})
        ws.conditional_format(rango, {"type": "text", "criteria": "begins with", "value": "No", "format": rojo})

    ws_c = wb.add_worksheet("CONTROL")
    ws_cl = wb.add_worksheet("CLASES")
    ws_ev = wb.add_worksheet("EVALUACIONES")
    ws_oa = wb.add_worksheet("OA BASALES")
    ws_ot = wb.add_worksheet("OAT")
    ws_ay = wb.add_worksheet("LEEME")

    # ------------------- CLASES -------------------
    ws_cl.write(0, 0, "CLASES PLANIFICADAS vs BASES CURRICULARES", titulo)
    ws_cl.write(1, 0, "Una fila por clase. Las columnas amarillas las completa UTP. "
                      "«Revisión automática» compara el objetivo de la clase con el OA oficial (orientativa).", sub)
    HC = 3
    for j, h in enumerate(H_CLASES):
        ws_cl.write(HC, j, h, head_utp if h in ("Fecha de la clase", "¿Clase creada?", "Observación UTP") else head)
    ws_cl.set_row(HC, 34)
    r = HC + 1
    filas_clase = {}
    for p, res in zip(planes, resultados):
        for x in res["clases"]:
            c = x["clase"]
            m = manual["clases"].get((p.docente, p.asignatura, p.unidad, str(c.n)), {})
            vals = [p.docente, p.asignatura, p.unidad, c.n, c.oa_txt or "—", c.objetivo,
                    "—" if x["existe"] is None else ("✔ Sí" if x["existe"] else "✖ No"),
                    "✔ Sí" if x["en_basales"] else "✖ No",
                    x["oficial"], x["estado"], x["sugerido"] or x["mejor"]]
            for j, v in enumerate(vals):
                ws_cl.write(r, j, v, txt_c if j in (3, 4, 6, 7, 9, 10) else txt)
            if m.get("Fecha de la clase"):
                ws_cl.write_datetime(r, 11, datetime.combine(m["Fecha de la clase"], datetime.min.time()), utp_fecha)
            else:
                ws_cl.write_blank(r, 11, None, utp_fecha)
            ws_cl.write(r, 12, m.get("¿Clase creada?", ""), utp_c)
            ws_cl.write(r, 13, m.get("Observación UTP", ""), utp_txt)
            ws_cl.set_row(r, max(32, 15 * (1 + len(x["oficial"]) // 55 + x["oficial"].count("\n") * 0)))
            filas_clase[(p.clave, c.n)] = m.get("¿Clase creada?", "")
            r += 1
    ult_cl = r
    for j, w in enumerate([18, 14, 11, 7, 11, 46, 11, 11, 58, 13, 12, 12, 11, 30]):
        ws_cl.set_column(j, j, w)
    if ult_cl > HC + 1:
        ws_cl.data_validation(HC + 1, 12, ult_cl - 1, 12, {"validate": "list", "source": ["Sí", "No"]})
        estado_cf(ws_cl, f"G{HC + 2}:H{ult_cl}")
        estado_cf(ws_cl, f"J{HC + 2}:J{ult_cl}")
        estado_cf(ws_cl, f"M{HC + 2}:M{ult_cl}")
        ws_cl.autofilter(HC, 0, ult_cl - 1, len(H_CLASES) - 1)
    ws_cl.freeze_panes(HC + 1, 6)
    ws_cl.set_landscape()
    ws_cl.fit_to_pages(1, 0)

    # ------------------- EVALUACIONES -------------------
    ws_ev.write(0, 0, "EVALUACIONES DE LA UNIDAD vs BASES CURRICULARES", titulo)
    ws_ev.write(1, 0, "Una fila por evaluación planificada. Las columnas amarillas las completa UTP.", sub)
    for j, h in enumerate(H_EVALS):
        ws_ev.write(HC, j, h, head_utp if h in ("¿Evaluación creada?", "Fecha de entrega", "Observación UTP") else head)
    ws_ev.set_row(HC, 34)
    r = HC + 1
    for p, res in zip(planes, resultados):
        for x in res["evals"]:
            e = x["eval"]
            m = manual["evals"].get((p.docente, p.asignatura, p.unidad, str(e.n)), {})
            vals = [p.docente, p.asignatura, p.unidad, e.n, e.tipo, e.oa_txt or "—", e.instrumento, e.procedimiento,
                    "—" if x["existe"] is None else ("✔ Sí" if x["existe"] else "✖ No"), "✔ Sí" if x["trabajado"] else "⚠ No",
                    x["estado"], x["sugerido"] or x["mejor"]]
            for j, v in enumerate(vals):
                ws_ev.write(r, j, v, txt_c if j in (3, 4, 5, 8, 9, 10, 11) else txt)
            ws_ev.write(r, 12, m.get("¿Evaluación creada?", ""), utp_c)
            if m.get("Fecha de entrega"):
                ws_ev.write_datetime(r, 13, datetime.combine(m["Fecha de entrega"], datetime.min.time()), utp_fecha)
            else:
                ws_ev.write_blank(r, 13, None, utp_fecha)
            ws_ev.write(r, 14, m.get("Observación UTP", ""), utp_txt)
            ws_ev.set_row(r, 48)
            r += 1
    ult_ev = r
    for j, w in enumerate([18, 14, 11, 6, 11, 10, 28, 44, 11, 13, 13, 12, 12, 12, 30]):
        ws_ev.set_column(j, j, w)
    if ult_ev > HC + 1:
        ws_ev.data_validation(HC + 1, 12, ult_ev - 1, 12, {"validate": "list", "source": ["Sí", "No"]})
        estado_cf(ws_ev, f"I{HC + 2}:K{ult_ev}")
        estado_cf(ws_ev, f"M{HC + 2}:M{ult_ev}")
        ws_ev.autofilter(HC, 0, ult_ev - 1, len(H_EVALS) - 1)
    ws_ev.freeze_panes(HC + 1, 6)
    ws_ev.set_landscape()
    ws_ev.fit_to_pages(1, 0)

    # ------------------- OA BASALES -------------------
    ws_oa.write(0, 0, "OA DE LA UNIDAD: ¿ESTÁN CUBIERTOS?", titulo)
    ws_oa.write(1, 0, "Cada OA declarado como basal (o usado en clases) y cuántas clases/evaluaciones lo trabajan.", sub)
    for j, h in enumerate(H_BASALES):
        ws_oa.write(HC, j, h, head)
    ws_oa.set_row(HC, 34)
    r = HC + 1
    for p, res in zip(planes, resultados):
        for b in res["basales"]:
            vals = [p.docente, p.asignatura, p.unidad, f"OA{b['oa']}", b["oficial"], b["n_clases"], b["n_evals"],
                    b["estado"]]
            for j, v in enumerate(vals):
                ws_oa.write(r, j, v, txt_c if j in (3, 5, 6) else txt)
            ws_oa.set_row(r, max(32, 16 * (1 + b["oficial"].count("\n") * 2)))
            r += 1
    for j, w in enumerate([18, 14, 11, 7, 78, 12, 13, 30]):
        ws_oa.set_column(j, j, w)
    if r > HC + 1:
        estado_cf(ws_oa, f"H{HC + 2}:H{r}")
        ws_oa.autofilter(HC, 0, r - 1, len(H_BASALES) - 1)
    ws_oa.freeze_panes(HC + 1, 4)
    ws_oa.set_landscape()
    ws_oa.fit_to_pages(1, 0)

    # ------------------- OAT -------------------
    ws_ot.write(0, 0, "OBJETIVOS DE APRENDIZAJE TRANSVERSALES (OAT) DECLARADOS", titulo)
    ws_ot.write(1, 0, "Las Bases no numeran los OAT: se numeran en el orden en que aparecen (OAT1 = primero de la dimensión física … "
                      "OAT34 = último de TIC). La columna de clases es una pista por palabras, no un veredicto.", sub)
    for j, h in enumerate(H_OAT):
        ws_ot.write(HC, j, h, head)
    ws_ot.set_row(HC, 34)
    r = HC + 1
    for p, res in zip(planes, resultados):
        filas = res["oat"] or [{"n": "", "dimension": "", "texto": "", "relacion": "",
                                "estado": "⚠ La planificación no declara OAT"}]
        for b in filas:
            vals = [p.docente, p.asignatura, p.unidad, f"OAT{b['n']}" if b["n"] != "" else "", b["dimension"],
                    b["texto"], b["relacion"], b["estado"]]
            for j, v in enumerate(vals):
                ws_ot.write(r, j, v, txt_c if j == 3 else txt)
            ws_ot.set_row(r, max(32, 16 * (1 + len(b["texto"]) // 70)))
            r += 1
    for j, w in enumerate([18, 14, 11, 7, 22, 70, 30, 34]):
        ws_ot.set_column(j, j, w)
    if r > HC + 1:
        estado_cf(ws_ot, f"H{HC + 2}:H{r}")
        ws_ot.autofilter(HC, 0, r - 1, len(H_OAT) - 1)
    ws_ot.freeze_panes(HC + 1, 4)
    ws_ot.set_landscape()
    ws_ot.fit_to_pages(1, 0)

    # ------------------- CONTROL -------------------
    ws = ws_c
    ws.write(0, 0, "CONTROL DE PLANIFICACIÓN POR UNIDAD · UTP", titulo)
    ws.write(1, 0, "Fecha de revisión:", sub)
    ws.write_formula(1, 1, "=TODAY()", hoy_f, (hoy - date(1899, 12, 30)).days)
    ws.write(2, 0, "Semáforo:  CUMPLE = al día y sin alertas  ·  REVISAR = pequeño atraso o alertas con las Bases  ·  "
                   "NO CUMPLE = atraso mayor a 20 puntos o unidad cerrada sin evaluaciones  ·  "
                   "POR MARCAR = UTP aún no marca «¿Clase creada?» en la hoja CLASES", sub)
    HR = 4
    grupos = [(0, 7, "DOCENTE Y FECHAS", banda), (8, 10, "CLASES CREADAS", banda), (11, 12, "EVALUACIONES", banda),
              (13, 15, "RESULTADO", banda_utp)]
    for a, b, t, fm in grupos:
        ws.merge_range(HR - 1, a, HR - 1, b, t, fm)
    for j, h in enumerate(H_CONTROL):
        ws.write(HR, j, h, head_utp if h == "Observaciones UTP" else head)
    ws.set_row(HR, 48)

    rng = lambda nombre, c: f"{nombre}!${col(c)}:${col(c)}"
    r = HR + 1
    resumen_consola = []
    for p, res in zip(planes, resultados):
        n_cl = len(p.clases)
        n_ev = len(p.evaluaciones)
        marcas = [filas_clase.get((p.clave, c.n), "") for c in p.clases]
        creadas = sum(1 for v in marcas if v == "Sí")
        revisadas = sum(1 for v in marcas if v in ("Sí", "No"))
        mev = [manual["evals"].get((p.docente, p.asignatura, p.unidad, str(e.n)), {}).get("¿Evaluación creada?", "")
               for e in p.evaluaciones]
        ev_ok = sum(1 for v in mev if v == "Sí")
        if p.inicio and p.cierre:
            estado = "Por iniciar" if hoy < p.inicio else ("Cerrada" if hoy > p.cierre else "En curso")
            dur = (p.cierre - p.inicio).days
            esperado = max(0.0, min(1.0, (hoy - p.inicio).days / dur)) if dur > 0 else 1.0
        else:
            estado, esperado = "Sin fecha", ""
        real = creadas / n_cl if n_cl else ""
        alertas_txt = "\n".join("• " + a for a in res["alertas"]) if res["alertas"] else "Sin alertas"
        semv = semaforo_py(estado, esperado if esperado != "" else 0, real if real != "" else 0, revisadas, n_ev,
                           ev_ok, bool(res["alertas"]))
        obs = manual["control"].get(p.clave, {}).get("Observaciones UTP", "")
        x = r + 1  # fila Excel (1-index)
        ws.write(r, 0, p.docente, txt_b)
        ws.write(r, 1, p.asignatura, txt)
        ws.write(r, 2, p.curso, txt_c)
        ws.write(r, 3, p.unidad, txt_c)
        if p.inicio:
            ws.write_datetime(r, 4, datetime.combine(p.inicio, datetime.min.time()), fecha)
        else:
            ws.write(r, 4, p.inicio_txt or "—", txt_c)
        if p.cierre:
            ws.write_datetime(r, 5, datetime.combine(p.cierre, datetime.min.time()), fecha)
        else:
            ws.write(r, 5, p.cierre_txt or "—", txt_c)
        ws.write_formula(r, 6, f'=IF(OR(E{x}="",F{x}="",NOT(ISNUMBER(E{x})),NOT(ISNUMBER(F{x}))),"Sin fecha",'
                               f'IF($B$2<E{x},"Por iniciar",IF($B$2>F{x},"Cerrada","En curso")))', txt_c, estado)
        ws.write_formula(r, 7, f'=IF(G{x}="Sin fecha","",MAX(0,MIN(1,($B$2-E{x})/(F{x}-E{x}))))', pct, esperado)
        ws.write_number(r, 8, n_cl, num)
        crit = (f'{rng("CLASES", 0)},$A{x},{rng("CLASES", 1)},$B{x},{rng("CLASES", 2)},$D{x}')
        ws.write_formula(r, 9, f'=COUNTIFS({crit},{rng("CLASES", 12)},"Sí")', num, creadas)
        ws.write_formula(r, 10, f'=IF(I{x}=0,"",J{x}/I{x})', pct, real)
        ws.write_number(r, 11, n_ev, num)
        critE = (f'{rng("EVALUACIONES", 0)},$A{x},{rng("EVALUACIONES", 1)},$B{x},{rng("EVALUACIONES", 2)},$D{x}')
        ws.write_formula(r, 12, f'=COUNTIFS({critE},{rng("EVALUACIONES", 12)},"Sí")', num, ev_ok)
        ws.write(r, 13, alertas_txt, txt)
        marc = f'COUNTIFS({crit},{rng("CLASES", 12)},"?*")'
        ws.write_formula(
            r, 14,
            f'=IF(G{x}="Sin fecha","SIN FECHA",IF({marc}=0,"POR MARCAR",'
            f'IF(AND(G{x}="Cerrada",M{x}<L{x}),"NO CUMPLE",'
            f'IF(H{x}-N(K{x})>0.2,"NO CUMPLE",'
            f'IF(OR(H{x}-N(K{x})>0.0001,N{x}<>"Sin alertas"),"REVISAR","CUMPLE")))))', sem, semv)
        ws.write(r, 15, obs, utp_txt)
        ws.set_row(r, max(60, 16 * (len(res["alertas"]) * 2 + 1)))
        resumen_consola.append((p, estado, semv, len(res["alertas"])))
        r += 1
    ult = r
    for j, w in enumerate([18, 16, 9, 10, 11, 11, 12, 12, 11, 10, 12, 12, 12, 58, 14, 32]):
        ws.set_column(j, j, w)
    if ult > HR + 1:
        semaforo_cf(ws, f"O{HR + 2}:O{ult}")
        estado_cf(ws, f"G{HR + 2}:G{ult}")
        ws.conditional_format(f"G{HR + 2}:G{ult}", {"type": "cell", "criteria": "==", "value": '"En curso"',
                                                     "format": ambar})
        ws.conditional_format(f"G{HR + 2}:G{ult}", {"type": "cell", "criteria": "==", "value": '"Cerrada"',
                                                     "format": gris})
        ws.conditional_format(f"G{HR + 2}:G{ult}", {"type": "cell", "criteria": "==", "value": '"Por iniciar"',
                                                     "format": gris})
        ws.conditional_format(f"N{HR + 2}:N{ult}", {"type": "cell", "criteria": "==", "value": '"Sin alertas"',
                                                     "format": verde})
        ws.autofilter(HR, 0, ult - 1, len(H_CONTROL) - 1)
    ws.freeze_panes(HR + 1, 1)
    ws.set_landscape()
    ws.set_paper(9)
    ws.fit_to_pages(1, 0)
    ws.activate()

    # ------------------- LEEME -------------------
    ws_ay.set_column(0, 0, 3)
    ws_ay.set_column(1, 1, 120)
    ws_ay.write(0, 1, "CÓMO USAR ESTE CONTROL", titulo)
    lineas = [
        ("1. Hoja CONTROL", True),
        ("Una fila por docente y unidad. Se mira de izquierda a derecha: fechas → clases creadas → evaluaciones → semáforo.", False),
        ("«Avance esperado» = qué porcentaje de la unidad debería estar listo según las fechas de inicio y cierre (se calcula con la fecha de hoy).", False),
        ("«Avance real» = porcentaje de clases que UTP marcó como creadas (hoja CLASES, columna «¿Clase creada?»).", False),
        ("", False),
        ("2. Qué completa UTP (celdas amarillas)", True),
        ("CLASES → «¿Clase creada?» (Sí / No), fecha de la clase y observación.  EVALUACIONES → «¿Evaluación creada?», fecha de entrega y observación.", False),
        ("CONTROL → «Observaciones UTP». Todo lo demás se calcula solo.", False),
        ("", False),
        ("3. Semáforo", True),
        ("CUMPLE: el avance real alcanza lo esperado por fechas y no hay alertas con las Bases.", False),
        ("REVISAR: atraso pequeño (hasta 20 puntos) o hay alertas (OA que no calzan, OA sin clase, etc.).", False),
        ("NO CUMPLE: atraso de más de 20 puntos, o la unidad ya cerró y faltan evaluaciones.", False),
        ("POR MARCAR: todavía no se ha marcado ninguna clase como «Sí/No». SIN FECHA: no se entiende la fecha de inicio/cierre.", False),
        ("", False),
        ("4. «Revisión automática» (hojas CLASES y EVALUACIONES)", True),
        ("El programa compara las palabras del objetivo de la clase con el texto oficial del OA que el docente citó, en 7° y 8° básico.", False),
        ("«Coincide» = el OA citado está entre los más parecidos al objetivo. «Parcial» = calza en un nivel (7° u 8°) pero no en el otro, porque los números de OA difieren entre niveles. «Revisar» = parece corresponder a otro OA (se sugiere cuál por nivel). ", False),
        ("Es una ayuda para ordenar la revisión: la decisión final siempre es de UTP (el docente puede tener una razón pedagógica).", False),
        ("", False),
        ("5. Actualizar el control", True),
        ("Vuelva a ejecutar el script con las planificaciones nuevas y el mismo nombre de Excel de salida: se conservan las marcas y observaciones ya escritas.", False),
        ("Cierre el Excel antes de volver a ejecutar el script.", False),
        ("", False),
        ("Nota: si la planificación no trae fecha por clase, el control usa solo la fecha de inicio y cierre de la unidad.", False),
        ("«OAT» = Objetivos de Aprendizaje Transversales. La hoja OAT muestra los que declara la planificación con el texto oficial de las Bases. "
         "Como las Bases no los numeran, se cuentan en orden (OAT1 a OAT34); si el colegio usa otra numeración, avíselo para ajustarla.", False),
        (f"Versión del motor de revisión: {VERSION}", False),
    ]
    tit = f(bold=True, font_color=AZUL, font_size=12)
    par = f(text_wrap=True, valign="top")
    rr = 2
    for t, es_tit in lineas:
        ws_ay.write(rr, 1, t, tit if es_tit else par)
        rr += 1

    wb.close()
    return resumen_consola


# --------------------------------------------------------------------------
# Programa principal
# --------------------------------------------------------------------------

def juntar_docx(entradas):
    archivos = []
    for e in entradas:
        p = Path(e)
        if p.is_dir():
            archivos += sorted(x for x in p.glob("*.docx") if not x.name.startswith("~$"))
        elif p.exists():
            archivos.append(p)
        else:
            print(f"  (aviso) no existe: {p}")
    return archivos


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="Genera un Excel de control para UTP comparando planificaciones (.docx) con las Bases Curriculares.")
    ap.add_argument("planificaciones", nargs="+", help="uno o más .docx, o una carpeta con .docx")
    ap.add_argument("--bases", required=True, help="Bases Curriculares 7° a 2° medio (.txt o .pdf)")
    ap.add_argument("--salida", default="Control_UTP.xlsx", help="Excel de salida (por defecto Control_UTP.xlsx)")
    ap.add_argument("--anio", type=int, default=date.today().year,
                    help="año para fechas escritas como «05 DE OCTUBRE» (por defecto el año actual)")
    ap.add_argument("--hoy", help="fecha de revisión AAAA-MM-DD (por defecto, hoy)")
    a = ap.parse_args()

    hoy = datetime.strptime(a.hoy, "%Y-%m-%d").date() if a.hoy else date.today()
    archivos = juntar_docx(a.planificaciones)
    if not archivos:
        sys.exit("ERROR: no encontré ninguna planificación .docx.")

    print("Leyendo Bases Curriculares ...")
    lineas_bases = leer_texto_bases(a.bases)
    bases = extraer_oa_lengua(lineas_bases)
    oat_bases = extraer_oat(lineas_bases)
    if not bases:
        print("  (aviso) no pude ubicar los OA de Lengua y Literatura en las bases: se omite la comparación.")
    else:
        print(f"  OA encontrados: 7° = {len(bases[7])}, 8° = {len(bases[8])}")
    comp = Comparador(bases) if bases else None

    planes = []
    for arch in archivos:
        print(f"Leyendo planificación: {arch.name}")
        try:
            encontrados = leer_planificaciones(arch, a.anio)
        except Exception as e:
            print(f"  (aviso) no pude leer {arch.name}: {e}")
            continue
        if not encontrados:
            print("  (aviso) no encontré una tabla de planificación en este archivo.")
        planes += encontrados
    if not planes:
        sys.exit("ERROR: no se pudo leer ninguna planificación.")

    resultados = []
    for p in planes:
        if bases and "LENGUA" not in norm(p.asignatura).upper() and "lengua" not in norm(p.asignatura):
            print(f"  (aviso) {p.docente}: la asignatura «{p.asignatura}» no es Lengua; "
                  "solo se revisan fechas, clases y evaluaciones (sin comparar con OA).")
            resultados.append(analizar(p, {}, None, oat_bases))
        else:
            resultados.append(analizar(p, bases, comp, oat_bases) if bases else analizar(p, {}, None, oat_bases))

    salida = Path(a.salida)
    manual = leer_manual(salida)
    try:
        resumen = escribir_excel(planes, resultados, salida, hoy, manual)
    except PermissionError:
        sys.exit(f"ERROR: no puedo escribir {salida}. ¿Está abierto en Excel? Ciérrelo y vuelva a ejecutar.")

    print("\nResumen")
    print("-" * 78)
    for p, estado, sem, n_al in resumen:
        ini = p.inicio.strftime("%d/%m") if p.inicio else "?"
        fin = p.cierre.strftime("%d/%m") if p.cierre else "?"
        print(f"{p.docente} | {p.asignatura} {p.curso} | {p.unidad} | {ini}-{fin} | {estado} | "
              f"{len(p.clases)} clases, {len(p.evaluaciones)} eval. | {n_al} alerta(s) | {sem}")
    print("-" * 78)
    print(f"Excel generado: {salida.resolve()}")


if __name__ == "__main__":
    main()
