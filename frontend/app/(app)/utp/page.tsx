"use client";

import { useEffect, useMemo, useState } from "react";
import { apiUpload, downloadFile } from "@/lib/api";
import { formatDate } from "@/lib/dates";

type SummaryRow = {
  docente: string;
  archivo: string;
  asignatura: string;
  curso: string;
  unidad: string;
  inicio: string;
  cierre: string;
  estado: string;
  clases: number;
  evaluaciones: number;
  alertas: number;
  semaforo: string;
  detalle_alertas: string[];
  etiqueta: string;
};

type ClaseRow = {
  planificacion: string;
  n: number;
  oa_citado: string;
  objetivo: string;
  revision: string;
  oa_sugerido: string;
  en_basales: boolean;
};

type EvalRow = {
  planificacion: string;
  n: number;
  tipo: string;
  oa_citado: string;
  instrumento: string;
  procedimiento: string;
  revision: string;
  oa_sugerido: string;
  trabajado: boolean;
};

type BasalRow = {
  planificacion: string;
  oa: string;
  oficial: string;
  clases: number;
  evaluaciones: number;
  estado: string;
};

type OatRow = {
  planificacion: string;
  oat: string;
  dimension: string;
  texto: string;
  relacion: string;
  estado: string;
};

type Analysis = {
  analysis_id: string;
  download_url: string;
  engine_version: string;
  anio: number;
  fecha_revision: string;
  bases: { nombre: string; oa: Record<string, number> };
  resumen: SummaryRow[];
  clases: ClaseRow[];
  evaluaciones: EvalRow[];
  basales: BasalRow[];
  oat: OatRow[];
  avisos: string[];
};

type Tab = "clases" | "evaluaciones" | "basales" | "oat";

const TABS: { id: Tab; label: string }[] = [
  { id: "clases", label: "Clases" },
  { id: "evaluaciones", label: "Evaluaciones" },
  { id: "basales", label: "OA basales" },
  { id: "oat", label: "OAT" },
];

function semaforoTone(value: string): string {
  if (value === "CUMPLE") return "ok";
  if (value === "REVISAR") return "warn";
  if (value === "NO CUMPLE") return "bad";
  return "none";
}

function revisionTone(value: string): string {
  if (value.startsWith("Coincide") || value.startsWith("✔")) return "ok";
  if (value.startsWith("Revisar") || value.startsWith("Parcial") || value.startsWith("⚠"))
    return "warn";
  return "bad";
}

function formatMaybeDate(value: string): string {
  if (!value) return "—";
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? formatDate(value) : value;
}

function todayISO(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
}

export default function UtpPage() {
  const [anio, setAnio] = useState(String(new Date().getFullYear()));
  const [fechaRevision, setFechaRevision] = useState(todayISO());
  const [planes, setPlanes] = useState<File[]>([]);
  const [bases, setBases] = useState<File | null>(null);
  const [previo, setPrevio] = useState<File | null>(null);
  const [inputKey, setInputKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Analysis | null>(null);

  const [tab, setTab] = useState<Tab>("clases");
  const [planFilter, setPlanFilter] = useState("Todas");
  const [onlyReview, setOnlyReview] = useState(false);

  useEffect(() => {
    setPlanFilter("Todas");
    setOnlyReview(false);
    setTab("clases");
  }, [result]);

  const counts = useMemo(() => {
    const base: Record<string, number> = {
      CUMPLE: 0,
      REVISAR: 0,
      "NO CUMPLE": 0,
      "POR MARCAR": 0,
    };
    for (const row of result?.resumen ?? []) {
      base[row.semaforo] = (base[row.semaforo] ?? 0) + 1;
    }
    return base;
  }, [result]);

  function filtered<T extends { planificacion: string }>(rows: T[]): T[] {
    return planFilter === "Todas"
      ? rows
      : rows.filter((row) => row.planificacion === planFilter);
  }

  const clases = useMemo(() => {
    const rows = filtered(result?.clases ?? []);
    return onlyReview ? rows.filter((row) => !row.revision.startsWith("Coincide")) : rows;
  }, [result, planFilter, onlyReview]);

  const evaluaciones = useMemo(() => filtered(result?.evaluaciones ?? []), [result, planFilter]);
  const basales = useMemo(() => filtered(result?.basales ?? []), [result, planFilter]);
  const oat = useMemo(() => filtered(result?.oat ?? []), [result, planFilter]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!planes.length) {
      setError("Selecciona al menos una planificación en Word (.docx).");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const formData = new FormData();
      for (const file of planes) formData.append("planificaciones", file);
      if (bases) formData.append("bases", bases);
      if (previo) formData.append("previo", previo);
      formData.append("anio", anio);
      formData.append("fecha_revision", fechaRevision);
      const data = await apiUpload<Analysis>("/utp/analyze", formData);
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron analizar las planificaciones");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setResult(null);
    setPlanes([]);
    setBases(null);
    setPrevio(null);
    setInputKey((key) => key + 1);
    setError("");
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Control UTP</h1>
          <p>
            Revisa planificaciones de unidad en Word contra las Bases Curriculares y descarga el
            Excel de control.
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="card">
        <form onSubmit={submit}>
          <div className="form-grid">
            <div>
              <label htmlFor="utp-anio">Año de las fechas</label>
              <input
                id="utp-anio"
                type="number"
                min={2000}
                max={2100}
                value={anio}
                onChange={(e) => setAnio(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="utp-fecha">Fecha de revisión</label>
              <input
                id="utp-fecha"
                type="date"
                value={fechaRevision}
                onChange={(e) => setFechaRevision(e.target.value)}
              />
            </div>
            <div className="full">
              <label htmlFor="utp-planes">Planificaciones (.docx)</label>
              <input
                key={`planes-${inputKey}`}
                id="utp-planes"
                type="file"
                accept=".docx"
                multiple
                onChange={(e) => setPlanes(Array.from(e.target.files ?? []))}
              />
              <p className="muted small-text">
                {planes.length
                  ? `${planes.length} archivo(s): ${planes.map((file) => file.name).join(", ")}`
                  : "Puedes subir varias planificaciones a la vez."}
              </p>
            </div>
            <div>
              <label htmlFor="utp-bases">Bases Curriculares (.txt o .pdf) — opcional</label>
              <input
                key={`bases-${inputKey}`}
                id="utp-bases"
                type="file"
                accept=".txt,.pdf"
                onChange={(e) => setBases(e.target.files?.[0] ?? null)}
              />
              <p className="muted small-text">
                {bases
                  ? bases.name
                  : "Si no subes Bases, se usan las de Lengua y Literatura 7° y 8° incluidas."}
              </p>
            </div>
            <div>
              <label htmlFor="utp-previo">Control UTP anterior (.xlsx) — opcional</label>
              <input
                key={`previo-${inputKey}`}
                id="utp-previo"
                type="file"
                accept=".xlsx"
                onChange={(e) => setPrevio(e.target.files?.[0] ?? null)}
              />
              <p className="muted small-text">
                {previo
                  ? previo.name
                  : "Conserva las clases creadas, fechas y observaciones escritas a mano."}
              </p>
            </div>
          </div>
          <div className="toolbar" style={{ marginTop: 14 }}>
            <button className="btn" type="submit" disabled={busy || !planes.length}>
              {busy ? "Analizando..." : "Analizar planificaciones"}
            </button>
            {result && (
              <button className="btn secondary" type="button" onClick={reset}>
                Nuevo análisis
              </button>
            )}
          </div>
        </form>
      </div>

      {result && (
        <>
          <div className="toolbar" style={{ marginTop: 18 }}>
            <button
              className="btn"
              onClick={() =>
                downloadFile(
                  result.download_url,
                  `Control_UTP_${result.fecha_revision}.xlsx`,
                )
              }
            >
              Descargar Excel de control
            </button>
            <span className="muted small-text">
              Motor {result.engine_version} · revisión del {formatDate(result.fecha_revision)}
            </span>
          </div>

          <div className="mini-stats" style={{ marginTop: 14 }}>
            <div className="mini-stat">
              <div className="n">{result.resumen.length}</div>
              <div className="l">Planificaciones</div>
            </div>
            <div className="mini-stat">
              <div className="n ok">{counts.CUMPLE}</div>
              <div className="l">Cumple</div>
            </div>
            <div className="mini-stat">
              <div className="n warn">{counts.REVISAR}</div>
              <div className="l">Revisar</div>
            </div>
            <div className="mini-stat">
              <div className="n bad">{counts["NO CUMPLE"]}</div>
              <div className="l">No cumple</div>
            </div>
            <div className="mini-stat">
              <div className="n none">{counts["POR MARCAR"]}</div>
              <div className="l">Por marcar</div>
            </div>
          </div>

          {result.bases.oa["7"] !== undefined && (
            <div className="notice" style={{ marginTop: 12 }}>
              Bases leídas: {result.bases.oa["7"]} OA de 7° y {result.bases.oa["8"] ?? 0} OA de 8°
              (Lengua y Literatura) · {result.bases.nombre}
            </div>
          )}

          {result.avisos.map((aviso) => (
            <div className="alert" key={aviso}>
              {aviso}
            </div>
          ))}

          <div className="card" style={{ marginTop: 16 }}>
            <h2>Resumen</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Docente</th>
                    <th>Asignatura</th>
                    <th>Curso</th>
                    <th>Unidad</th>
                    <th>Inicio</th>
                    <th>Cierre</th>
                    <th>Clases</th>
                    <th>Evaluaciones</th>
                    <th>Alertas</th>
                    <th>Semáforo</th>
                  </tr>
                </thead>
                <tbody>
                  {result.resumen.map((row) => (
                    <tr key={`${row.etiqueta}-${row.archivo}`}>
                      <td>{row.docente || "—"}</td>
                      <td>{row.asignatura}</td>
                      <td>{row.curso || "—"}</td>
                      <td>{row.unidad}</td>
                      <td>{formatMaybeDate(row.inicio)}</td>
                      <td>{formatMaybeDate(row.cierre)}</td>
                      <td>{row.clases}</td>
                      <td>{row.evaluaciones}</td>
                      <td>
                        {row.detalle_alertas.length ? (
                          <details>
                            <summary>{row.alertas}</summary>
                            <ul className="small-text">
                              {row.detalle_alertas.map((alerta) => (
                                <li key={alerta}>{alerta}</li>
                              ))}
                            </ul>
                          </details>
                        ) : (
                          "0"
                        )}
                      </td>
                      <td>
                        <span className={`badge ${semaforoTone(row.semaforo)}`}>
                          {row.semaforo}
                        </span>
                        <div className="muted small-text">{row.estado}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <div className="page-head" style={{ marginBottom: 10 }}>
              <div>
                <h2>Detalle</h2>
                <p className="muted small-text">
                  Revisión de OA citados, evaluaciones y cobertura de las Bases.
                </p>
              </div>
              <div className="toolbar" style={{ margin: 0 }}>
                <select
                  aria-label="Filtrar por planificación"
                  value={planFilter}
                  onChange={(e) => setPlanFilter(e.target.value)}
                >
                  <option value="Todas">Todas las planificaciones</option>
                  {result.resumen.map((row) => (
                    <option key={`${row.etiqueta}-${row.archivo}`} value={row.etiqueta}>
                      {row.etiqueta}
                    </option>
                  ))}
                </select>
                {tab === "clases" && (
                  <label className="small-text" style={{ display: "flex", gap: 6 }}>
                    <input
                      type="checkbox"
                      checked={onlyReview}
                      onChange={(e) => setOnlyReview(e.target.checked)}
                    />
                    Solo por revisar
                  </label>
                )}
              </div>
            </div>

            <div className="toolbar" style={{ marginBottom: 10 }}>
              {TABS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`btn small ${tab === item.id ? "" : "secondary"}`}
                  onClick={() => setTab(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>

            <div className="table-wrap">
              {tab === "clases" && (
                <table>
                  <thead>
                    <tr>
                      <th>Planificación</th>
                      <th>N°</th>
                      <th>OA citado</th>
                      <th>Objetivo de la clase</th>
                      <th>Revisión</th>
                      <th>OA que más se parece</th>
                      <th>¿En basales?</th>
                    </tr>
                  </thead>
                  <tbody>
                    {clases.map((row) => (
                      <tr key={`${row.planificacion}-${row.n}`}>
                        <td>{row.planificacion}</td>
                        <td>{row.n}</td>
                        <td>{row.oa_citado || "—"}</td>
                        <td>{row.objetivo || "—"}</td>
                        <td>
                          <span className={`badge ${revisionTone(row.revision)}`}>
                            {row.revision}
                          </span>
                        </td>
                        <td>{row.oa_sugerido || "—"}</td>
                        <td>{row.en_basales ? "Sí" : "No"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {tab === "evaluaciones" && (
                <table>
                  <thead>
                    <tr>
                      <th>Planificación</th>
                      <th>N°</th>
                      <th>Tipo</th>
                      <th>OA citado</th>
                      <th>Instrumento</th>
                      <th>Procedimiento</th>
                      <th>Revisión</th>
                      <th>OA que más se parece</th>
                      <th>¿OA trabajado en clases?</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evaluaciones.map((row) => (
                      <tr key={`${row.planificacion}-eval-${row.n}`}>
                        <td>{row.planificacion}</td>
                        <td>{row.n}</td>
                        <td>{row.tipo}</td>
                        <td>{row.oa_citado || "—"}</td>
                        <td>{row.instrumento || "—"}</td>
                        <td>{row.procedimiento || "—"}</td>
                        <td>
                          <span className={`badge ${revisionTone(row.revision)}`}>
                            {row.revision}
                          </span>
                        </td>
                        <td>{row.oa_sugerido || "—"}</td>
                        <td>{row.trabajado ? "Sí" : "No"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {tab === "basales" && (
                <table>
                  <thead>
                    <tr>
                      <th>Planificación</th>
                      <th>OA</th>
                      <th>Qué dicen las Bases</th>
                      <th>Clases</th>
                      <th>Evaluaciones</th>
                      <th>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {basales.map((row) => (
                      <tr key={`${row.planificacion}-basal-${row.oa}`}>
                        <td>{row.planificacion}</td>
                        <td>{row.oa}</td>
                        <td>{row.oficial}</td>
                        <td>{row.clases}</td>
                        <td>{row.evaluaciones}</td>
                        <td>
                          <span className={`badge ${revisionTone(row.estado)}`}>
                            {row.estado}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {tab === "oat" && (
                <>
                  <p className="muted small-text" style={{ marginBottom: 8 }}>
                    Las Bases no numeran los OAT: se cuentan en orden de aparición. La columna de
                    clases es una pista por palabras.
                  </p>
                  <table>
                    <thead>
                      <tr>
                        <th>Planificación</th>
                        <th>OAT</th>
                        <th>Dimensión</th>
                        <th>Qué dicen las Bases</th>
                        <th>Clases o evaluaciones relacionadas (pista)</th>
                        <th>Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {oat.map((row) => (
                        <tr key={`${row.planificacion}-${row.oat}`}>
                          <td>{row.planificacion}</td>
                          <td>{row.oat}</td>
                          <td>{row.dimension}</td>
                          <td>{row.texto}</td>
                          <td>{row.relacion || "—"}</td>
                          <td>
                            <span className={`badge ${revisionTone(row.estado)}`}>
                              {row.estado}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </div>

            {tab === "clases" && clases.length === 0 && (
              <div className="empty">No hay clases que mostrar con los filtros actuales.</div>
            )}
            {tab === "evaluaciones" && evaluaciones.length === 0 && (
              <div className="empty">No hay evaluaciones en las planificaciones analizadas.</div>
            )}
            {tab === "basales" && basales.length === 0 && (
              <div className="empty">No hay OA basales declarados.</div>
            )}
            {tab === "oat" && oat.length === 0 && (
              <div className="empty">No hay OAT declarados.</div>
            )}
          </div>
        </>
      )}
    </>
  );
}
