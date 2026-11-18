"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { monthISO, monthRange, todayISO } from "@/lib/dates";
import { formatRut } from "@/lib/rut";

type Course = { id: number; name: string; year: number };
type Status = "presente" | "ausente" | "atrasado" | "justificado";
type StatusValue = Status | "";

type DayRow = {
  student_id: number;
  full_name: string;
  rut: string;
  status: Status | null;
  note: string | null;
  record_id: number | null;
};

type DaySummary = {
  presente: number;
  ausente: number;
  atrasado: number;
  justificado: number;
  sin_marcar: number;
};

type DayData = {
  course: Course;
  date: string;
  items: DayRow[];
  summary: DaySummary;
};

type SummaryRow = {
  student_id: number;
  full_name: string;
  rut: string;
  presente: number;
  ausente: number;
  atrasado: number;
  justificado: number;
  total: number;
  rate: number | null;
};

type SummaryData = {
  course: Course;
  from_date: string;
  to_date: string;
  days: number;
  items: SummaryRow[];
  summary: {
    presente: number;
    ausente: number;
    atrasado: number;
    justificado: number;
    total: number;
    rate: number | null;
  };
};

const STATUS_OPTIONS: { value: Status; label: string }[] = [
  { value: "presente", label: "Presente" },
  { value: "ausente", label: "Ausente" },
  { value: "atrasado", label: "Atrasado" },
  { value: "justificado", label: "Justificado" },
];

function rateTone(rate: number | null): string {
  if (rate == null) return "none";
  if (rate >= 85) return "ok";
  if (rate >= 70) return "warn";
  return "bad";
}

export default function AsistenciaPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [coursesReady, setCoursesReady] = useState(false);
  const [courseId, setCourseId] = useState("");
  const [day, setDay] = useState(todayISO());
  const [tab, setTab] = useState<"dia" | "mes">("dia");
  const [month, setMonth] = useState(monthISO());

  const [data, setData] = useState<DayData | null>(null);
  const [statuses, setStatuses] = useState<Record<number, StatusValue>>({});
  const [dirty, setDirty] = useState(false);
  const [monthData, setMonthData] = useState<SummaryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMonth, setLoadingMonth] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    api<{ items: Course[] }>("/courses?limit=200")
      .then((result) => {
        setCourses(result.items);
        if (result.items.length) setCourseId((prev) => prev || String(result.items[0].id));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Error al cargar los cursos"))
      .finally(() => setCoursesReady(true));
  }, []);

  const loadDay = useCallback(async (cid: string, date: string) => {
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const result = await api<DayData>(`/attendance/day?course_id=${cid}&date=${date}`);
      setData(result);
      const next: Record<number, StatusValue> = {};
      for (const item of result.items) next[item.student_id] = item.status ?? "";
      setStatuses(next);
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la asistencia");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!courseId) {
      setData(null);
      return;
    }
    loadDay(courseId, day);
  }, [courseId, day, loadDay]);

  const loadMonth = useCallback(async (cid: string, selectedMonth: string) => {
    setLoadingMonth(true);
    setError("");
    try {
      const range = monthRange(selectedMonth);
      const result = await api<SummaryData>(
        `/attendance/summary?course_id=${cid}&from=${range.from}&to=${range.to}`,
      );
      setMonthData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el resumen");
      setMonthData(null);
    } finally {
      setLoadingMonth(false);
    }
  }, []);

  useEffect(() => {
    if (courseId && tab === "mes") loadMonth(courseId, month);
  }, [courseId, month, tab, loadMonth]);

  const counts = useMemo(() => {
    const result: DaySummary = { presente: 0, ausente: 0, atrasado: 0, justificado: 0, sin_marcar: 0 };
    if (!data) return result;
    for (const item of data.items) {
      const value = statuses[item.student_id];
      if (value) result[value] += 1;
      else result.sin_marcar += 1;
    }
    return result;
  }, [data, statuses]);

  function changeStatus(studentId: number, status: Status) {
    setStatuses((prev) => ({ ...prev, [studentId]: prev[studentId] === status ? "" : status }));
    setDirty(true);
    setNotice("");
  }

  function markAllPresent() {
    if (!data) return;
    const next: Record<number, StatusValue> = {};
    for (const item of data.items) next[item.student_id] = "presente";
    setStatuses(next);
    setDirty(true);
    setNotice("");
  }

  async function save() {
    if (!data) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const result = await api<DayData>("/attendance/day", {
        method: "PUT",
        body: {
          course_id: data.course.id,
          date: data.date,
          items: data.items.map((item) => ({
            student_id: item.student_id,
            status: statuses[item.student_id] || null,
            note: item.note,
          })),
        },
      });
      setData(result);
      const next: Record<number, StatusValue> = {};
      for (const item of result.items) next[item.student_id] = item.status ?? "";
      setStatuses(next);
      setDirty(false);
      setMonthData(null);
      setNotice("Asistencia guardada.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar la asistencia");
    } finally {
      setSaving(false);
    }
  }

  const course = courses.find((c) => String(c.id) === courseId);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Asistencia</h1>
          <p>Marca la asistencia del día y revisa el resumen mensual de cada curso.</p>
        </div>
        {tab === "dia" && data && data.items.length > 0 && (
          <div style={{ display: "flex", gap: 10 }}>
            <button className="btn secondary" onClick={markAllPresent} disabled={saving}>
              Todos presentes
            </button>
            <button className="btn" onClick={save} disabled={saving || !dirty}>
              {saving ? "Guardando..." : dirty ? "Guardar asistencia" : "Guardado"}
            </button>
          </div>
        )}
      </div>

      <div className="filters">
        <div>
          <label htmlFor="course">Curso</label>
          <select
            id="course"
            value={courseId}
            onChange={(e) => {
              setCourseId(e.target.value);
              setData(null);
              setMonthData(null);
              setDirty(false);
            }}
          >
            <option value="">Selecciona un curso</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.year})
              </option>
            ))}
          </select>
        </div>
        {tab === "dia" ? (
          <div>
            <label htmlFor="day">Día</label>
            <input
              id="day"
              type="date"
              value={day}
              max={todayISO()}
              onChange={(e) => {
                setDay(e.target.value);
                setDirty(false);
              }}
            />
          </div>
        ) : (
          <div>
            <label htmlFor="month">Mes</label>
            <input id="month" type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
          </div>
        )}
      </div>

      <div className="tabs">
        <button className={`tab ${tab === "dia" ? "active" : ""}`} onClick={() => setTab("dia")}>
          Por día
        </button>
        <button className={`tab ${tab === "mes" ? "active" : ""}`} onClick={() => setTab("mes")}>
          Resumen mensual
        </button>
      </div>

      {error && <div className="alert">{error}</div>}
      {notice && <div className="notice">{notice}</div>}

      {coursesReady && courses.length === 0 && (
        <div className="empty-state">
          Aún no hay cursos. <Link href="/cursos">Crea un curso</Link> para registrar asistencia.
        </div>
      )}

      {coursesReady && courses.length > 0 && !courseId && (
        <div className="empty-state">Selecciona un curso para comenzar.</div>
      )}

      {tab === "dia" && courseId && (
        <>
          <div className="mini-stats">
            <div className="mini-stat presente">
              <div className="n">{counts.presente}</div>
              <div className="l">Presentes</div>
            </div>
            <div className="mini-stat ausente">
              <div className="n">{counts.ausente}</div>
              <div className="l">Ausentes</div>
            </div>
            <div className="mini-stat atrasado">
              <div className="n">{counts.atrasado}</div>
              <div className="l">Atrasados</div>
            </div>
            <div className="mini-stat justificado">
              <div className="n">{counts.justificado}</div>
              <div className="l">Justificados</div>
            </div>
            <div className="mini-stat sin-marcar">
              <div className="n">{counts.sin_marcar}</div>
              <div className="l">Sin marcar</div>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Estudiante</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((item) => (
                  <tr key={item.student_id}>
                    <td>
                      <strong>{item.full_name}</strong>
                      <div className="muted small-text">{formatRut(item.rut)}</div>
                    </td>
                    <td>
                      <div className="seg">
                        {STATUS_OPTIONS.map((option) => (
                          <button
                            key={option.value}
                            type="button"
                            className={`seg-btn ${option.value} ${
                              statuses[item.student_id] === option.value ? "active" : ""
                            }`}
                            onClick={() => changeStatus(item.student_id, option.value)}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {loading && <div className="empty">Cargando asistencia...</div>}
            {!loading && data && data.items.length === 0 && (
              <div className="empty">
                {course?.name} no tiene estudiantes activos.{" "}
                <Link href="/estudiantes">Asigna estudiantes al curso</Link>.
              </div>
            )}
            {!loading && !data && <div className="empty">No se pudo cargar la asistencia.</div>}
          </div>

          <p className="muted small-text" style={{ marginTop: 10 }}>
            Puedes dejar a un estudiante sin marcar y completarlo después. Haz clic en el mismo estado
            para quitarlo.
          </p>
        </>
      )}

      {tab === "mes" && courseId && (
        <>
          <div className="mini-stats">
            <div className="mini-stat">
              <div className={`n ${rateTone(monthData?.summary.rate ?? null)}`}>
                {monthData?.summary.rate == null ? "—" : `${monthData.summary.rate}%`}
              </div>
              <div className="l">Asistencia del curso</div>
            </div>
            <div className="mini-stat">
              <div className="n">{monthData?.days ?? 0}</div>
              <div className="l">Días con registro</div>
            </div>
            <div className="mini-stat">
              <div className="n">{monthData?.summary.total ?? 0}</div>
              <div className="l">Marcas en el período</div>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Estudiante</th>
                  <th>Presente</th>
                  <th>Ausente</th>
                  <th>Atrasado</th>
                  <th>Justificado</th>
                  <th>Asistencia</th>
                </tr>
              </thead>
              <tbody>
                {monthData?.items.map((row) => (
                  <tr key={row.student_id}>
                    <td>
                      <strong>{row.full_name}</strong>
                      <div className="muted small-text">{formatRut(row.rut)}</div>
                    </td>
                    <td>{row.presente}</td>
                    <td>{row.ausente}</td>
                    <td>{row.atrasado}</td>
                    <td>{row.justificado}</td>
                    <td>
                      <span className={`badge ${rateTone(row.rate)}`}>
                        {row.rate == null ? "Sin registros" : `${row.rate}%`}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {loadingMonth && <div className="empty">Cargando resumen...</div>}
            {!loadingMonth && monthData && monthData.items.length === 0 && (
              <div className="empty">Este curso no tiene estudiantes activos.</div>
            )}
            {!loadingMonth && !monthData && <div className="empty">No se pudo cargar el resumen.</div>}
          </div>

          <p className="muted small-text" style={{ marginTop: 10 }}>
            El porcentaje considera como asistencia los estados &quot;Presente&quot; y &quot;Atrasado&quot;.
          </p>
        </>
      )}
    </>
  );
}
