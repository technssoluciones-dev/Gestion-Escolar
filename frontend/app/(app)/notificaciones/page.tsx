"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { formatDate, monthISO } from "@/lib/dates";

type NotificationType = "inasistencia" | "notas" | "deuda" | "general";
type NotificationStatus = "pendiente" | "enviada";

type Notification = {
  id: number;
  student_id: number;
  guardian_id: number | null;
  type: NotificationType;
  period: string;
  title: string;
  message: string;
  status: NotificationStatus;
  channel: string;
  created_at: string;
  sent_at: string | null;
  student_name: string;
  student_rut: string;
  course_name: string | null;
  guardian_name: string | null;
  guardian_email: string | null;
  guardian_phone: string | null;
};

type Summary = { pending: number; sent: number; by_type: Record<string, number> };
type Course = { id: number; name: string; year: number };
type Student = {
  id: number;
  full_name: string;
  rut: string;
  course: { id: number; name: string } | null;
  guardian: { id: number; full_name: string } | null;
};

const TYPE_LABELS: Record<NotificationType, string> = {
  inasistencia: "Inasistencia",
  notas: "Notas",
  deuda: "Deuda",
  general: "General",
};

const TYPE_TONES: Record<NotificationType, string> = {
  inasistencia: "warn",
  notas: "info",
  deuda: "bad",
  general: "none",
};

const GENERATE_TYPES: NotificationType[] = ["inasistencia", "notas", "deuda"];

type ManualForm = {
  studentId: string;
  type: NotificationType;
  title: string;
  message: string;
  period: string;
};

function monthLabel(period: string): string {
  const months = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
  ];
  const [year, month] = period.split("-");
  return months[Number(month) - 1] ? `${months[Number(month) - 1]} ${year}` : period;
}

function emptyManual(): ManualForm {
  return {
    studentId: "",
    type: "general",
    title: "",
    message: "",
    period: monthISO(),
  };
}

export default function NotificacionesPage() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [courseFilter, setCourseFilter] = useState("");
  const [version, setVersion] = useState(0);
  const [sendingId, setSendingId] = useState<number | null>(null);
  const [sendingChannel, setSendingChannel] = useState<"email" | "whatsapp" | null>(null);

  const [generateOpen, setGenerateOpen] = useState(false);
  const [generatePeriod, setGeneratePeriod] = useState(monthISO());
  const [generateTypes, setGenerateTypes] = useState<NotificationType[]>([
    "inasistencia",
    "notas",
    "deuda",
  ]);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState("");

  const [manual, setManual] = useState<ManualForm | null>(null);
  const [manualError, setManualError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setReady(false);
    Promise.all([
      api<{ items: Notification[] }>("/notifications?limit=200"),
      api<Summary>("/notifications/summary"),
      api<{ items: Course[] }>("/courses?limit=200"),
      api<{ items: Student[] }>("/students?limit=200"),
    ])
      .then(([list, counts, courseData, studentData]) => {
        setNotifications(list.items);
        setSummary(counts);
        setCourses(courseData.items);
        setStudents(studentData.items);
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "No se pudieron cargar los avisos"),
      )
      .finally(() => setReady(true));
  }, [version]);

  const visible = useMemo(() => {
    const text = query.trim().toLowerCase();
    return notifications.filter((item) => {
      if (statusFilter && item.status !== statusFilter) return false;
      if (typeFilter && item.type !== typeFilter) return false;
      if (courseFilter && item.course_name !== courseFilter) return false;
      if (!text) return true;
      return `${item.student_name} ${item.student_rut} ${item.title} ${item.message}`
        .toLowerCase()
        .includes(text);
    });
  }, [notifications, query, statusFilter, typeFilter, courseFilter]);

  async function toggleStatus(item: Notification) {
    setError("");
    try {
      await api(`/notifications/${item.id}`, {
        method: "PUT",
        body: { status: item.status === "enviada" ? "pendiente" : "enviada" },
      });
      setNotice(
        item.status === "enviada"
          ? "El aviso volvió a quedar pendiente."
          : "Aviso marcado como enviado. Ya está visible en el portal de la familia.",
      );
      setVersion((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo actualizar el aviso");
    }
  }

  async function sendEmail(item: Notification) {
    if (!item.guardian_email) {
      setError("El apoderado no tiene correo registrado.");
      return;
    }
    setSendingId(item.id);
    setSendingChannel("email");
    setError("");
    setNotice("");
    try {
      await api(`/notifications/${item.id}/email`, { method: "POST" });
      setNotice(`Aviso enviado por correo a ${item.guardian_email}.`);
      setVersion((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo enviar el correo");
    } finally {
      setSendingId(null);
      setSendingChannel(null);
    }
  }

  async function sendWhatsApp(item: Notification) {
    if (!item.guardian_phone) {
      setError("El apoderado no tiene teléfono registrado.");
      return;
    }
    setSendingId(item.id);
    setSendingChannel("whatsapp");
    setError("");
    setNotice("");
    try {
      await api(`/notifications/${item.id}/whatsapp`, { method: "POST" });
      setNotice(`Aviso enviado por WhatsApp a ${item.guardian_phone}.`);
      setVersion((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo enviar el WhatsApp");
    } finally {
      setSendingId(null);
      setSendingChannel(null);
    }
  }

  async function remove(item: Notification) {
    if (!window.confirm(`¿Eliminar el aviso "${item.title}" de ${item.student_name}?`)) return;
    setError("");
    try {
      await api(`/notifications/${item.id}`, { method: "DELETE" });
      setNotice("Aviso eliminado.");
      setVersion((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo eliminar el aviso");
    }
  }

  async function generate(e: FormEvent) {
    e.preventDefault();
    setGenerateError("");
    if (generateTypes.length === 0) {
      setGenerateError("Selecciona al menos un motivo de aviso.");
      return;
    }
    setGenerating(true);
    try {
      const result = await api<{
        created: number;
        skipped: number;
        by_type: Record<string, number>;
      }>("/notifications/generate", {
        method: "POST",
        body: { period: generatePeriod, types: generateTypes },
      });
      const pieces = Object.entries(result.by_type)
        .map(([type, count]) => `${count} de ${TYPE_LABELS[type as NotificationType] ?? type}`)
        .join(", ");
      if (result.created > 0) {
        setNotice(
          `Se generaron ${result.created} avisos${pieces ? ` (${pieces})` : ""}.` +
            (result.skipped ? ` ${result.skipped} ya existían.` : ""),
        );
      } else if (result.skipped > 0) {
        setNotice(`No hay avisos nuevos: los ${result.skipped} ya existían para ese período.`);
      } else {
        setNotice("No se encontraron casos que ameriten un aviso en ese período.");
      }
      setGenerateOpen(false);
      setVersion((v) => v + 1);
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : "No se pudieron generar los avisos");
    } finally {
      setGenerating(false);
    }
  }

  async function submitManual(e: FormEvent) {
    e.preventDefault();
    if (!manual) return;
    setManualError("");
    setSaving(true);
    try {
      await api("/notifications", {
        method: "POST",
        body: {
          student_id: Number(manual.studentId),
          type: manual.type,
          title: manual.title,
          message: manual.message,
          period: manual.period,
        },
      });
      setNotice("Aviso creado. Queda pendiente hasta que lo marques como enviado.");
      setManual(null);
      setVersion((v) => v + 1);
    } catch (err) {
      setManualError(err instanceof Error ? err.message : "No se pudo crear el aviso");
    } finally {
      setSaving(false);
    }
  }

  const selectedStudent = students.find((s) => String(s.id) === manual?.studentId);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Notificaciones</h1>
          <p>
            Genera avisos por inasistencia, notas o deuda, revísalos y publícalos en el portal de
            las familias.
          </p>
        </div>
        <div className="row-actions" style={{ justifyContent: "flex-start" }}>
          <button className="btn" onClick={() => {
            setGenerateError("");
            setGeneratePeriod(monthISO());
            setGenerateOpen(true);
          }}>
            Generar avisos
          </button>
          <button className="btn secondary" onClick={() => {
            setManualError("");
            setManual(emptyManual());
          }}>
            + Aviso manual
          </button>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}
      {notice && <div className="notice">{notice}</div>}

      <div className="mini-stats">
        <div className="mini-stat">
          <div className="n warn">{summary?.pending ?? 0}</div>
          <div className="l">Pendientes de envío</div>
        </div>
        <div className="mini-stat">
          <div className="n ok">{summary?.sent ?? 0}</div>
          <div className="l">Enviadas</div>
        </div>
        <div className="mini-stat">
          <div className="n">{summary?.by_type.inasistencia ?? 0}</div>
          <div className="l">Por inasistencia</div>
        </div>
        <div className="mini-stat">
          <div className="n">{summary?.by_type.notas ?? 0}</div>
          <div className="l">Por notas</div>
        </div>
        <div className="mini-stat">
          <div className="n">{summary?.by_type.deuda ?? 0}</div>
          <div className="l">Por deuda</div>
        </div>
      </div>

      <div className="toolbar">
        <input
          placeholder="Buscar estudiante, RUT o aviso"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Todos los estados</option>
          <option value="pendiente">Pendientes</option>
          <option value="enviada">Enviadas</option>
        </select>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="">Todos los motivos</option>
          <option value="inasistencia">Inasistencia</option>
          <option value="notas">Notas</option>
          <option value="deuda">Deuda</option>
          <option value="general">General</option>
        </select>
        <select value={courseFilter} onChange={(e) => setCourseFilter(e.target.value)}>
          <option value="">Todos los cursos</option>
          {courses.map((course) => (
            <option key={course.id} value={course.name}>
              {course.name} ({course.year})
            </option>
          ))}
        </select>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Estudiante</th>
              <th>Aviso</th>
              <th>Apoderado</th>
              <th>Período</th>
              <th>Estado</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((item) => (
              <tr key={item.id}>
                <td>
                  <strong>{item.student_name}</strong>
                  <div className="muted small-text">
                    {item.student_rut}
                    {item.course_name ? ` · ${item.course_name}` : ""}
                  </div>
                </td>
                <td>
                  <span className={`badge ${TYPE_TONES[item.type]}`}>
                    {TYPE_LABELS[item.type]}
                  </span>
                  <div style={{ marginTop: 4 }}>
                    <strong>{item.title}</strong>
                  </div>
                  <div className="muted small-text msg-cell">{item.message}</div>
                </td>
                <td>
                  {item.guardian_name ?? <span className="muted">Sin apoderado</span>}
                  {item.guardian_email && (
                    <div className="muted small-text">{item.guardian_email}</div>
                  )}
                  {item.guardian_phone && (
                    <div className="muted small-text">{item.guardian_phone}</div>
                  )}
                </td>
                <td>{monthLabel(item.period)}</td>
                <td>
                  <span className={`badge ${item.status === "enviada" ? "ok" : "warn"}`}>
                    {item.status === "enviada" ? "Enviada" : "Pendiente"}
                  </span>
                  <div className="muted small-text">
                    {item.status === "enviada" && item.sent_at
                      ? `Enviada el ${formatDate(item.sent_at)}`
                      : `Creada el ${formatDate(item.created_at)}`}
                  </div>
                </td>
                <td>
                  <div className="row-actions">
                    {item.status !== "enviada" && (
                      <button
                        className="btn small"
                        disabled={!item.guardian_email || sendingId !== null}
                        title={
                          item.guardian_email
                            ? `Enviar a ${item.guardian_email}`
                            : "El apoderado no tiene correo registrado"
                        }
                        onClick={() => sendEmail(item)}
                      >
                        {sendingId === item.id && sendingChannel === "email"
                          ? "Enviando..."
                          : "Enviar por correo"}
                      </button>
                    )}
                    {item.status !== "enviada" && (
                      <button
                        className="btn small"
                        disabled={!item.guardian_phone || sendingId !== null}
                        title={
                          item.guardian_phone
                            ? `Enviar a ${item.guardian_phone}`
                            : "El apoderado no tiene teléfono registrado"
                        }
                        onClick={() => sendWhatsApp(item)}
                      >
                        {sendingId === item.id && sendingChannel === "whatsapp"
                          ? "Enviando..."
                          : "Enviar WhatsApp"}
                      </button>
                    )}
                    <button className="btn secondary small" onClick={() => toggleStatus(item)}>
                      {item.status === "enviada" ? "Volver a pendiente" : "Marcar enviada"}
                    </button>
                    <button className="btn danger small" onClick={() => remove(item)}>
                      Eliminar
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {ready && visible.length === 0 && (
              <tr>
                <td colSpan={6} className="empty">
                  No hay avisos que coincidan con los filtros. Usa “Generar avisos” para detectar
                  inasistencias, promedios bajo 4.0 o deudas vencidas.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {generateOpen && (
        <div
          className="overlay"
          onMouseDown={(e) => e.target === e.currentTarget && setGenerateOpen(false)}
        >
          <form className="modal" onSubmit={generate}>
            <div className="modal-head">
              <h2>Generar avisos automáticos</h2>
              <button
                type="button"
                className="btn secondary small"
                onClick={() => setGenerateOpen(false)}
              >
                ✕
              </button>
            </div>

            {generateError && <div className="alert">{generateError}</div>}

            <div className="form-grid">
              <div>
                <label htmlFor="gen-period">
                  Período <span className="req">*</span>
                </label>
                <input
                  id="gen-period"
                  type="month"
                  required
                  value={generatePeriod}
                  onChange={(e) => setGeneratePeriod(e.target.value)}
                />
              </div>
              <div className="full">
                <label>Motivos</label>
                {GENERATE_TYPES.map((type) => (
                  <div key={type} className="checkbox-row" style={{ paddingTop: 0 }}>
                    <input
                      id={`gen-${type}`}
                      type="checkbox"
                      checked={generateTypes.includes(type)}
                      onChange={(e) =>
                        setGenerateTypes((current) =>
                          e.target.checked
                            ? [...current, type]
                            : current.filter((t) => t !== type),
                        )
                      }
                    />
                    <label htmlFor={`gen-${type}`}>{TYPE_LABELS[type]}</label>
                  </div>
                ))}
                <p className="muted small-text" style={{ marginTop: 8 }}>
                  Se avisa por inasistencia bajo 85% (con al menos 5 registros), promedio general
                  bajo 4.0 o cobros vencidos con saldo. No se duplican avisos del mismo período.
                </p>
              </div>
            </div>

            <div className="modal-foot">
              <button
                type="button"
                className="btn secondary"
                onClick={() => setGenerateOpen(false)}
              >
                Cancelar
              </button>
              <button className="btn" disabled={generating}>
                {generating ? "Generando..." : "Generar avisos"}
              </button>
            </div>
          </form>
        </div>
      )}

      {manual && (
        <div
          className="overlay"
          onMouseDown={(e) => e.target === e.currentTarget && setManual(null)}
        >
          <form className="modal" onSubmit={submitManual}>
            <div className="modal-head">
              <h2>Nuevo aviso</h2>
              <button type="button" className="btn secondary small" onClick={() => setManual(null)}>
                ✕
              </button>
            </div>

            {manualError && <div className="alert">{manualError}</div>}

            <div className="form-grid">
              <div className="full">
                <label htmlFor="manual-student">
                  Estudiante <span className="req">*</span>
                </label>
                <select
                  id="manual-student"
                  required
                  value={manual.studentId}
                  onChange={(e) => setManual({ ...manual, studentId: e.target.value })}
                >
                  <option value="">Selecciona un estudiante</option>
                  {students.map((student) => (
                    <option key={student.id} value={student.id}>
                      {student.full_name}
                      {student.course ? ` · ${student.course.name}` : ""}
                    </option>
                  ))}
                </select>
                <p className="muted small-text" style={{ margin: "6px 0 0" }}>
                  {selectedStudent?.guardian
                    ? `Se enviará a ${selectedStudent.guardian.full_name}.`
                    : "El estudiante no tiene apoderado registrado."}
                </p>
              </div>
              <div>
                <label htmlFor="manual-type">Motivo</label>
                <select
                  id="manual-type"
                  value={manual.type}
                  onChange={(e) =>
                    setManual({ ...manual, type: e.target.value as NotificationType })
                  }
                >
                  <option value="general">General</option>
                  <option value="inasistencia">Inasistencia</option>
                  <option value="notas">Notas</option>
                  <option value="deuda">Deuda</option>
                </select>
              </div>
              <div>
                <label htmlFor="manual-period">Período</label>
                <input
                  id="manual-period"
                  type="month"
                  required
                  value={manual.period}
                  onChange={(e) => setManual({ ...manual, period: e.target.value })}
                />
              </div>
              <div className="full">
                <label htmlFor="manual-title">
                  Título <span className="req">*</span>
                </label>
                <input
                  id="manual-title"
                  required
                  value={manual.title}
                  onChange={(e) => setManual({ ...manual, title: e.target.value })}
                  placeholder="Ej: Reunión de apoderados"
                />
              </div>
              <div className="full">
                <label htmlFor="manual-message">
                  Mensaje <span className="req">*</span>
                </label>
                <textarea
                  id="manual-message"
                  required
                  rows={4}
                  value={manual.message}
                  onChange={(e) => setManual({ ...manual, message: e.target.value })}
                  placeholder="Escribe el mensaje que verá la familia en el portal."
                />
              </div>
            </div>

            <div className="modal-foot">
              <button type="button" className="btn secondary" onClick={() => setManual(null)}>
                Cancelar
              </button>
              <button className="btn" disabled={saving}>
                {saving ? "Guardando..." : "Crear aviso"}
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
