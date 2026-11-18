"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, apiUpload, downloadFile } from "@/lib/api";
import { formatDate, todayISO } from "@/lib/dates";
import { formatRut, isValidRut } from "@/lib/rut";

type Course = { id: number; name: string; year: number; capacity: number };
type AdmissionStatus =
  | "postulada"
  | "en_revision"
  | "aceptada"
  | "rechazada"
  | "matriculada";

type Admission = {
  id: number;
  applicant_rut: string;
  full_name: string;
  first_name: string;
  last_name: string;
  birth_date: string;
  gender: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  guardian_first_name: string | null;
  guardian_last_name: string | null;
  guardian_rut: string | null;
  guardian_email: string | null;
  guardian_phone: string | null;
  course_id: number | null;
  course: { id: number; name: string; year: number } | null;
  year: number;
  status: AdmissionStatus;
  application_date: string;
  notes: string | null;
  student_id: number | null;
  student_name: string | null;
};

type DossierDocument = {
  id: number;
  admission_id: number;
  name: string;
  filename: string;
  content_type: string;
  size: number;
  uploaded_at: string;
};

type InterviewMode = "presencial" | "online" | "telefonica";
type InterviewStatus = "pendiente" | "realizada" | "cancelada";

type DossierInterview = {
  id: number;
  admission_id: number;
  scheduled_at: string;
  interviewer: string;
  mode: InterviewMode;
  status: InterviewStatus;
  notes: string | null;
  created_at: string;
};

type DossierScore = {
  id: number;
  admission_id: number;
  criterion: string;
  score: number;
  weight: number;
  notes: string | null;
};

type Dossier = {
  documents: DossierDocument[];
  interviews: DossierInterview[];
  scores: DossierScore[];
  weighted_score: number | null;
};

const INTERVIEW_MODE_LABELS: Record<InterviewMode, string> = {
  presencial: "Presencial",
  online: "Online",
  telefonica: "Telefónica",
};

const INTERVIEW_STATUS_LABELS: Record<InterviewStatus, string> = {
  pendiente: "Pendiente",
  realizada: "Realizada",
  cancelada: "Cancelada",
};

function interviewStatusTone(value: InterviewStatus): string {
  if (value === "realizada") return "ok";
  if (value === "pendiente") return "warn";
  return "none";
}

function scoreTone(value: number): string {
  if (value >= 75) return "ok";
  if (value >= 50) return "warn";
  return "bad";
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateTime(iso: string): string {
  return `${formatDate(iso)} ${iso.slice(11, 16)}`;
}

function emptyInterviewForm() {
  return {
    id: null as number | null,
    scheduled_at: "",
    interviewer: "",
    mode: "presencial" as InterviewMode,
    status: "pendiente" as InterviewStatus,
    notes: "",
  };
}

function emptyScoreForm() {
  return {
    id: null as number | null,
    criterion: "",
    score: "",
    weight: "1",
    notes: "",
  };
}

const STATUS_OPTIONS: { value: AdmissionStatus; label: string }[] = [
  { value: "postulada", label: "Postulada" },
  { value: "en_revision", label: "En revisión" },
  { value: "aceptada", label: "Aceptada" },
  { value: "rechazada", label: "Rechazada" },
  { value: "matriculada", label: "Matriculada" },
];

function statusLabel(value: AdmissionStatus): string {
  return STATUS_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

function statusTone(value: AdmissionStatus): string {
  if (value === "postulada") return "none";
  if (value === "en_revision") return "warn";
  if (value === "aceptada") return "ok";
  if (value === "rechazada") return "bad";
  return "info";
}

type FormState = {
  applicant_rut: string;
  first_name: string;
  last_name: string;
  birth_date: string;
  gender: string;
  email: string;
  phone: string;
  address: string;
  guardian_first_name: string;
  guardian_last_name: string;
  guardian_rut: string;
  guardian_email: string;
  guardian_phone: string;
  course_id: string;
  year: string;
  status: AdmissionStatus;
  application_date: string;
  notes: string;
};

function emptyForm(): FormState {
  return {
    applicant_rut: "",
    first_name: "",
    last_name: "",
    birth_date: "",
    gender: "",
    email: "",
    phone: "",
    address: "",
    guardian_first_name: "",
    guardian_last_name: "",
    guardian_rut: "",
    guardian_email: "",
    guardian_phone: "",
    course_id: "",
    year: String(new Date().getFullYear()),
    status: "postulada",
    application_date: todayISO(),
    notes: "",
  };
}

function formFrom(item: Admission): FormState {
  return {
    applicant_rut: formatRut(item.applicant_rut),
    first_name: item.first_name,
    last_name: item.last_name,
    birth_date: item.birth_date,
    gender: item.gender ?? "",
    email: item.email ?? "",
    phone: item.phone ?? "",
    address: item.address ?? "",
    guardian_first_name: item.guardian_first_name ?? "",
    guardian_last_name: item.guardian_last_name ?? "",
    guardian_rut: item.guardian_rut ? formatRut(item.guardian_rut) : "",
    guardian_email: item.guardian_email ?? "",
    guardian_phone: item.guardian_phone ?? "",
    course_id: item.course_id ? String(item.course_id) : "",
    year: String(item.year),
    status: item.status,
    application_date: item.application_date,
    notes: item.notes ?? "",
  };
}

function fullName(item: Admission): string {
  return item.guardian_first_name || item.guardian_last_name
    ? `${item.guardian_first_name ?? ""} ${item.guardian_last_name ?? ""}`.trim()
    : "—";
}

function guardianPhrase(item: Admission): string {
  if (!item.guardian_first_name && !item.guardian_last_name) return "";
  const name = `${item.guardian_first_name ?? ""} ${item.guardian_last_name ?? ""}`
    .replace(/\s+/g, " ")
    .trim();
  return ` y se asociará al apoderado ${name}`;
}

export default function AdmisionesPage() {
  const [items, setItems] = useState<Admission[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("todos");
  const [courseFilter, setCourseFilter] = useState("todos");

  const [modal, setModal] = useState<{ mode: "new" | "edit"; item?: Admission } | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);

  const [enrollItem, setEnrollItem] = useState<Admission | null>(null);
  const [enrollCourseId, setEnrollCourseId] = useState("");

  const [dossierItem, setDossierItem] = useState<Admission | null>(null);
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [dossierTab, setDossierTab] = useState<"documentos" | "entrevistas" | "puntajes">(
    "documentos",
  );
  const [dossierLoading, setDossierLoading] = useState(false);
  const [dossierError, setDossierError] = useState("");
  const [dossierNotice, setDossierNotice] = useState("");
  const [dossierSaving, setDossierSaving] = useState(false);
  const [docName, setDocName] = useState("");
  const [docFile, setDocFile] = useState<File | null>(null);
  const [docInputKey, setDocInputKey] = useState(0);
  const [interviewForm, setInterviewForm] = useState(emptyInterviewForm);
  const [scoreForm, setScoreForm] = useState(emptyScoreForm);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [admissionResult, courseResult] = await Promise.all([
        api<{ items: Admission[] }>("/admissions?limit=200"),
        api<{ items: Course[] }>("/courses?limit=200"),
      ]);
      setItems(admissionResult.items);
      setCourses(courseResult.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron cargar las postulaciones");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    const termRut = term.replace(/[.\s]/g, "");
    return items.filter((item) => {
      if (statusFilter !== "todos" && item.status !== statusFilter) return false;
      if (courseFilter !== "todos" && String(item.course_id ?? "") !== courseFilter) return false;
      if (!term) return true;
      return (
        item.full_name.toLowerCase().includes(term) ||
        item.applicant_rut.toLowerCase().includes(termRut) ||
        (item.guardian_rut ?? "").toLowerCase().includes(termRut)
      );
    });
  }, [items, query, statusFilter, courseFilter]);

  const counts = useMemo(
    () => ({
      total: items.length,
      pending: items.filter((item) => item.status === "postulada" || item.status === "en_revision")
        .length,
      accepted: items.filter((item) => item.status === "aceptada").length,
      enrolled: items.filter((item) => item.status === "matriculada").length,
    }),
    [items],
  );

  function openNew() {
    setError("");
    setNotice("");
    setForm(emptyForm());
    setModal({ mode: "new" });
  }

  function openEdit(item: Admission) {
    setError("");
    setNotice("");
    setForm(formFrom(item));
    setModal({ mode: "edit", item });
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!isValidRut(form.applicant_rut)) {
      setError("El RUT del postulante no es válido.");
      return;
    }
    if (form.guardian_rut.trim() && !isValidRut(form.guardian_rut)) {
      setError("El RUT del apoderado no es válido.");
      return;
    }
    if (form.guardian_rut.trim() && (!form.guardian_first_name.trim() || !form.guardian_last_name.trim())) {
      setError("Si indicas RUT del apoderado, completa su nombre y apellido.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const body = {
        applicant_rut: form.applicant_rut.trim(),
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        birth_date: form.birth_date,
        gender: form.gender || null,
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        address: form.address.trim() || null,
        guardian_first_name: form.guardian_first_name.trim() || null,
        guardian_last_name: form.guardian_last_name.trim() || null,
        guardian_rut: form.guardian_rut.trim() || null,
        guardian_email: form.guardian_email.trim() || null,
        guardian_phone: form.guardian_phone.trim() || null,
        course_id: form.course_id ? Number(form.course_id) : null,
        year: Number(form.year),
        status: form.status,
        application_date: form.application_date,
        notes: form.notes.trim() || null,
      };
      if (modal?.mode === "edit" && modal.item) {
        await api(`/admissions/${modal.item.id}`, { method: "PUT", body });
        setNotice("Postulación actualizada.");
      } else {
        await api("/admissions", { method: "POST", body });
        setNotice("Postulación registrada.");
      }
      setModal(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar la postulación");
    } finally {
      setSaving(false);
    }
  }

  async function remove(item: Admission) {
    if (!window.confirm(`¿Eliminar la postulación de ${item.full_name}?`)) return;
    setError("");
    setNotice("");
    try {
      await api(`/admissions/${item.id}`, { method: "DELETE" });
      setNotice("Postulación eliminada.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo eliminar la postulación");
    }
  }

  function openEnroll(item: Admission) {
    setError("");
    setNotice("");
    setEnrollItem(item);
    setEnrollCourseId(
      item.course_id ? String(item.course_id) : courses.length ? String(courses[0].id) : "",
    );
  }

  async function enroll(event: React.FormEvent) {
    event.preventDefault();
    if (!enrollItem) return;
    if (!enrollCourseId) {
      setError("Selecciona un curso para matricular.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await api(`/admissions/${enrollItem.id}/enroll`, {
        method: "POST",
        body: { course_id: Number(enrollCourseId) },
      });
      setNotice("Postulante matriculado. Se creó su ficha de estudiante.");
      setEnrollItem(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo matricular al postulante");
    } finally {
      setSaving(false);
    }
  }

  const selectedCourse = courses.find((course) => String(course.id) === enrollCourseId);

  async function loadDossier(admissionId: number) {
    setDossierLoading(true);
    try {
      setDossier(await api<Dossier>(`/admissions/${admissionId}/dossier`));
    } catch (e) {
      setDossierError(e instanceof Error ? e.message : "No se pudo cargar el expediente");
    } finally {
      setDossierLoading(false);
    }
  }

  function openDossier(item: Admission) {
    setDossierItem(item);
    setDossier(null);
    setDossierTab("documentos");
    setDossierError("");
    setDossierNotice("");
    setDocName("");
    setDocFile(null);
    setInterviewForm(emptyInterviewForm());
    setScoreForm(emptyScoreForm());
    loadDossier(item.id);
  }

  async function uploadDocument(event: React.FormEvent) {
    event.preventDefault();
    if (!dossierItem) return;
    if (!docFile) {
      setDossierError("Selecciona un archivo PDF, JPG o PNG.");
      return;
    }
    setDossierSaving(true);
    setDossierError("");
    setDossierNotice("");
    try {
      const formData = new FormData();
      formData.append("name", docName.trim());
      formData.append("file", docFile);
      await apiUpload(`/admissions/${dossierItem.id}/documents`, formData);
      setDocName("");
      setDocFile(null);
      setDocInputKey((key) => key + 1);
      setDossierNotice("Documento subido.");
      await loadDossier(dossierItem.id);
    } catch (e) {
      setDossierError(e instanceof Error ? e.message : "No se pudo subir el documento");
    } finally {
      setDossierSaving(false);
    }
  }

  async function removeDocument(document: DossierDocument) {
    if (!dossierItem || !window.confirm(`¿Eliminar el documento "${document.name}"?`)) return;
    setDossierError("");
    try {
      await api(`/admission-documents/${document.id}`, { method: "DELETE" });
      setDossierNotice("Documento eliminado.");
      await loadDossier(dossierItem.id);
    } catch (e) {
      setDossierError(e instanceof Error ? e.message : "No se pudo eliminar el documento");
    }
  }

  async function saveInterview(event: React.FormEvent) {
    event.preventDefault();
    if (!dossierItem) return;
    setDossierSaving(true);
    setDossierError("");
    setDossierNotice("");
    try {
      const body = {
        scheduled_at: interviewForm.scheduled_at,
        interviewer: interviewForm.interviewer.trim(),
        mode: interviewForm.mode,
        status: interviewForm.status,
        notes: interviewForm.notes.trim() || null,
      };
      if (interviewForm.id) {
        await api(`/admission-interviews/${interviewForm.id}`, { method: "PUT", body });
        setDossierNotice("Entrevista actualizada.");
      } else {
        await api(`/admissions/${dossierItem.id}/interviews`, { method: "POST", body });
        setDossierNotice("Entrevista agendada.");
      }
      setInterviewForm(emptyInterviewForm());
      await loadDossier(dossierItem.id);
    } catch (e) {
      setDossierError(e instanceof Error ? e.message : "No se pudo guardar la entrevista");
    } finally {
      setDossierSaving(false);
    }
  }

  function editInterview(interview: DossierInterview) {
    setInterviewForm({
      id: interview.id,
      scheduled_at: interview.scheduled_at.slice(0, 16),
      interviewer: interview.interviewer,
      mode: interview.mode,
      status: interview.status,
      notes: interview.notes ?? "",
    });
    setDossierError("");
    setDossierNotice("");
  }

  async function removeInterview(interview: DossierInterview) {
    if (!dossierItem || !window.confirm("¿Eliminar esta entrevista?")) return;
    setDossierError("");
    try {
      await api(`/admission-interviews/${interview.id}`, { method: "DELETE" });
      setDossierNotice("Entrevista eliminada.");
      if (interviewForm.id === interview.id) setInterviewForm(emptyInterviewForm());
      await loadDossier(dossierItem.id);
    } catch (e) {
      setDossierError(e instanceof Error ? e.message : "No se pudo eliminar la entrevista");
    }
  }

  async function saveScore(event: React.FormEvent) {
    event.preventDefault();
    if (!dossierItem) return;
    setDossierSaving(true);
    setDossierError("");
    setDossierNotice("");
    try {
      const body = {
        criterion: scoreForm.criterion.trim(),
        score: Number(scoreForm.score),
        weight: Number(scoreForm.weight),
        notes: scoreForm.notes.trim() || null,
      };
      if (scoreForm.id) {
        await api(`/admission-scores/${scoreForm.id}`, { method: "PUT", body });
        setDossierNotice("Puntaje actualizado.");
      } else {
        await api(`/admissions/${dossierItem.id}/scores`, { method: "POST", body });
        setDossierNotice("Puntaje registrado.");
      }
      setScoreForm(emptyScoreForm());
      await loadDossier(dossierItem.id);
    } catch (e) {
      setDossierError(e instanceof Error ? e.message : "No se pudo guardar el puntaje");
    } finally {
      setDossierSaving(false);
    }
  }

  function editScore(score: DossierScore) {
    setScoreForm({
      id: score.id,
      criterion: score.criterion,
      score: String(score.score),
      weight: String(score.weight),
      notes: score.notes ?? "",
    });
    setDossierError("");
    setDossierNotice("");
  }

  async function removeScore(score: DossierScore) {
    if (!dossierItem || !window.confirm(`¿Eliminar el puntaje "${score.criterion}"?`)) return;
    setDossierError("");
    try {
      await api(`/admission-scores/${score.id}`, { method: "DELETE" });
      setDossierNotice("Puntaje eliminado.");
      if (scoreForm.id === score.id) setScoreForm(emptyScoreForm());
      await loadDossier(dossierItem.id);
    } catch (e) {
      setDossierError(e instanceof Error ? e.message : "No se pudo eliminar el puntaje");
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Admisiones</h1>
          <p>Postulaciones de nuevos estudiantes y su paso a matrícula.</p>
        </div>
        <button className="btn" onClick={openNew}>
          Nueva postulación
        </button>
      </div>

      {error && <div className="alert">{error}</div>}
      {notice && <div className="notice">{notice}</div>}

      <div className="mini-stats">
        <div className="mini-stat">
          <div className="n">{counts.total}</div>
          <div className="l">Postulaciones</div>
        </div>
        <div className="mini-stat">
          <div className="n warn">{counts.pending}</div>
          <div className="l">Pendientes</div>
        </div>
        <div className="mini-stat">
          <div className="n ok">{counts.accepted}</div>
          <div className="l">Aceptadas</div>
        </div>
        <div className="mini-stat">
          <div className="n">{counts.enrolled}</div>
          <div className="l">Matriculadas</div>
        </div>
      </div>

      <div className="filters">
        <div>
          <label htmlFor="q">Buscar</label>
          <input
            id="q"
            type="search"
            placeholder="Nombre o RUT..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="status">Estado</label>
          <select id="status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="todos">Todos los estados</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="course-filter">Curso</label>
          <select
            id="course-filter"
            value={courseFilter}
            onChange={(e) => setCourseFilter(e.target.value)}
          >
            <option value="todos">Todos los cursos</option>
            {courses.map((course) => (
              <option key={course.id} value={course.id}>
                {course.name} ({course.year})
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Postulante</th>
              <th>Apoderado</th>
              <th>Curso</th>
              <th>Postulación</th>
              <th>Estado</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filtered.map((item) => (
              <tr key={item.id}>
                <td>
                  <strong>{item.full_name}</strong>
                  <div className="muted small-text">
                    {formatRut(item.applicant_rut)} · {formatDate(item.birth_date)}
                  </div>
                </td>
                <td>
                  {fullName(item)}
                  {item.guardian_rut && (
                    <div className="muted small-text">{formatRut(item.guardian_rut)}</div>
                  )}
                </td>
                <td>
                  {item.course ? (
                    <>
                      {item.course.name}
                      <div className="muted small-text">{item.year}</div>
                    </>
                  ) : (
                    <span className="muted">Sin curso</span>
                  )}
                </td>
                <td>{formatDate(item.application_date)}</td>
                <td>
                  <span className={`badge ${statusTone(item.status)}`}>
                    {statusLabel(item.status)}
                  </span>
                  {item.status === "matriculada" && item.student_name && (
                    <div className="muted small-text">Estudiante: {item.student_name}</div>
                  )}
                </td>
                <td>
                  <div className="row-actions">
                    <button className="btn small secondary" onClick={() => openDossier(item)}>
                      Expediente
                    </button>
                    {item.status !== "matriculada" && (
                      <>
                        <button className="btn small secondary" onClick={() => openEdit(item)}>
                          Editar
                        </button>
                        <button className="btn small" onClick={() => openEnroll(item)}>
                          Matricular
                        </button>
                        <button className="btn small danger" onClick={() => remove(item)}>
                          Eliminar
                        </button>
                      </>
                    )}
                  </div>
                  {item.status === "matriculada" && (
                    <div className="muted small-text" style={{ marginTop: 4 }}>
                      Ficha creada
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="empty">Cargando postulaciones...</div>}
        {!loading && filtered.length === 0 && (
          <div className="empty">
            {items.length === 0 ? (
              <>
                Aún no hay postulaciones.{" "}
                <button className="btn small" onClick={openNew}>
                  Registrar la primera
                </button>
              </>
            ) : (
              "No hay postulaciones que coincidan con los filtros."
            )}
          </div>
        )}
      </div>

      <p className="muted small-text" style={{ marginTop: 10 }}>
        Al matricular se crea la ficha del estudiante y, si corresponde, la del apoderado. El curso
        debe tener cupos disponibles.{" "}
        {counts.enrolled > 0 && <Link href="/estudiantes">Ver estudiantes</Link>}
      </p>

      {modal && (
        <div className="overlay">
          <div className="modal wide">
            <div className="modal-head">
              <h2>{modal.mode === "edit" ? "Editar postulación" : "Nueva postulación"}</h2>
              <button className="btn secondary small" onClick={() => setModal(null)}>
                Cerrar
              </button>
            </div>
            <form onSubmit={save}>
              <h3 className="form-section">Datos del postulante</h3>
              <div className="form-grid">
                <div>
                  <label htmlFor="applicant-rut">
                    RUT <span className="req">*</span>
                  </label>
                  <input
                    id="applicant-rut"
                    type="text"
                    placeholder="12.345.678-5"
                    value={form.applicant_rut}
                    onChange={(e) => setForm({ ...form, applicant_rut: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="birth-date">
                    Fecha de nacimiento <span className="req">*</span>
                  </label>
                  <input
                    id="birth-date"
                    type="date"
                    value={form.birth_date}
                    max={todayISO()}
                    onChange={(e) => setForm({ ...form, birth_date: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="first-name">
                    Nombre <span className="req">*</span>
                  </label>
                  <input
                    id="first-name"
                    type="text"
                    value={form.first_name}
                    onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="last-name">
                    Apellido <span className="req">*</span>
                  </label>
                  <input
                    id="last-name"
                    type="text"
                    value={form.last_name}
                    onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="gender">Género</label>
                  <select
                    id="gender"
                    value={form.gender}
                    onChange={(e) => setForm({ ...form, gender: e.target.value })}
                  >
                    <option value="">Sin especificar</option>
                    <option value="F">Femenino</option>
                    <option value="M">Masculino</option>
                    <option value="O">Otro</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="phone">Teléfono</label>
                  <input
                    id="phone"
                    type="text"
                    placeholder="+56 9 ..."
                    value={form.phone}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  />
                </div>
                <div className="full">
                  <label htmlFor="email">Correo</label>
                  <input
                    id="email"
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                  />
                </div>
                <div className="full">
                  <label htmlFor="address">Dirección</label>
                  <input
                    id="address"
                    type="text"
                    value={form.address}
                    onChange={(e) => setForm({ ...form, address: e.target.value })}
                  />
                </div>
              </div>

              <h3 className="form-section">Apoderado</h3>
              <div className="form-grid">
                <div>
                  <label htmlFor="guardian-first-name">Nombre</label>
                  <input
                    id="guardian-first-name"
                    type="text"
                    value={form.guardian_first_name}
                    onChange={(e) => setForm({ ...form, guardian_first_name: e.target.value })}
                  />
                </div>
                <div>
                  <label htmlFor="guardian-last-name">Apellido</label>
                  <input
                    id="guardian-last-name"
                    type="text"
                    value={form.guardian_last_name}
                    onChange={(e) => setForm({ ...form, guardian_last_name: e.target.value })}
                  />
                </div>
                <div>
                  <label htmlFor="guardian-rut">RUT</label>
                  <input
                    id="guardian-rut"
                    type="text"
                    placeholder="12.345.678-5"
                    value={form.guardian_rut}
                    onChange={(e) => setForm({ ...form, guardian_rut: e.target.value })}
                  />
                </div>
                <div>
                  <label htmlFor="guardian-phone">Teléfono</label>
                  <input
                    id="guardian-phone"
                    type="text"
                    placeholder="+56 9 ..."
                    value={form.guardian_phone}
                    onChange={(e) => setForm({ ...form, guardian_phone: e.target.value })}
                  />
                </div>
                <div className="full">
                  <label htmlFor="guardian-email">Correo</label>
                  <input
                    id="guardian-email"
                    type="email"
                    value={form.guardian_email}
                    onChange={(e) => setForm({ ...form, guardian_email: e.target.value })}
                  />
                </div>
              </div>

              <h3 className="form-section">Postulación</h3>
              <div className="form-grid">
                <div>
                  <label htmlFor="admission-course">Curso al que postula</label>
                  <select
                    id="admission-course"
                    value={form.course_id}
                    onChange={(e) => setForm({ ...form, course_id: e.target.value })}
                  >
                    <option value="">Sin curso definido</option>
                    {courses.map((course) => (
                      <option key={course.id} value={course.id}>
                        {course.name} ({course.year})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="admission-year">
                    Año <span className="req">*</span>
                  </label>
                  <input
                    id="admission-year"
                    type="number"
                    min="1900"
                    max="2100"
                    value={form.year}
                    onChange={(e) => setForm({ ...form, year: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="admission-status">Estado</label>
                  <select
                    id="admission-status"
                    value={form.status}
                    onChange={(e) =>
                      setForm({ ...form, status: e.target.value as AdmissionStatus })
                    }
                  >
                    {STATUS_OPTIONS.filter((option) => option.value !== "matriculada").map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="application-date">
                    Fecha de postulación <span className="req">*</span>
                  </label>
                  <input
                    id="application-date"
                    type="date"
                    value={form.application_date}
                    onChange={(e) => setForm({ ...form, application_date: e.target.value })}
                    required
                  />
                </div>
                <div className="full">
                  <label htmlFor="notes">Observaciones</label>
                  <textarea
                    id="notes"
                    rows={3}
                    value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  />
                </div>
              </div>

              <div className="modal-foot">
                <button type="button" className="btn secondary" onClick={() => setModal(null)}>
                  Cancelar
                </button>
                <button className="btn" disabled={saving}>
                  {saving ? "Guardando..." : "Guardar postulación"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {enrollItem && (
        <div className="overlay">
          <div className="modal">
            <div className="modal-head">
              <h2>Matricular postulante</h2>
              <button className="btn secondary small" onClick={() => setEnrollItem(null)}>
                Cerrar
              </button>
            </div>
            <form onSubmit={enroll}>
              <p>
                Se creará la ficha de <strong>{enrollItem.full_name}</strong> como estudiante
                activo{guardianPhrase(enrollItem)}.
              </p>
              <div>
                <label htmlFor="enroll-course">
                  Curso <span className="req">*</span>
                </label>
                <select
                  id="enroll-course"
                  value={enrollCourseId}
                  onChange={(e) => setEnrollCourseId(e.target.value)}
                  required
                >
                  <option value="">Selecciona un curso</option>
                  {courses.map((course) => (
                    <option key={course.id} value={course.id}>
                      {course.name} ({course.year}) · {course.capacity} cupos
                    </option>
                  ))}
                </select>
                {selectedCourse && (
                  <p className="muted small-text" style={{ marginBottom: 0 }}>
                    Capacidad del curso: {selectedCourse.capacity} estudiantes.
                  </p>
                )}
              </div>
              <div className="modal-foot">
                <button type="button" className="btn secondary" onClick={() => setEnrollItem(null)}>
                  Cancelar
                </button>
                <button className="btn" disabled={saving}>
                  {saving ? "Matriculando..." : "Matricular"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {dossierItem && (
        <div
          className="overlay"
          onMouseDown={(e) => e.target === e.currentTarget && setDossierItem(null)}
        >
          <div className="modal wide">
            <div className="modal-head">
              <h2>Expediente de {dossierItem.full_name}</h2>
              <button className="btn secondary small" onClick={() => setDossierItem(null)}>
                Cerrar
              </button>
            </div>

            <p className="muted small-text" style={{ marginTop: -8 }}>
              {formatRut(dossierItem.applicant_rut)} ·{" "}
              {dossierItem.course ? dossierItem.course.name : "Sin curso"} ·{" "}
              {statusLabel(dossierItem.status)}
              {dossier?.weighted_score != null && (
                <> · Puntaje ponderado: {dossier.weighted_score.toFixed(1)}</>
              )}
            </p>

            {dossierError && <div className="alert">{dossierError}</div>}
            {dossierNotice && <div className="notice">{dossierNotice}</div>}

            <div className="tabs">
              <button
                type="button"
                className={`tab ${dossierTab === "documentos" ? "active" : ""}`}
                onClick={() => setDossierTab("documentos")}
              >
                Documentos{dossier ? ` (${dossier.documents.length})` : ""}
              </button>
              <button
                type="button"
                className={`tab ${dossierTab === "entrevistas" ? "active" : ""}`}
                onClick={() => setDossierTab("entrevistas")}
              >
                Entrevistas{dossier ? ` (${dossier.interviews.length})` : ""}
              </button>
              <button
                type="button"
                className={`tab ${dossierTab === "puntajes" ? "active" : ""}`}
                onClick={() => setDossierTab("puntajes")}
              >
                Puntajes{dossier ? ` (${dossier.scores.length})` : ""}
              </button>
            </div>

            {dossierLoading ? (
              <p className="muted">Cargando expediente...</p>
            ) : !dossier ? null : dossierTab === "documentos" ? (
              <>
                <form onSubmit={uploadDocument}>
                  <div className="form-grid">
                    <div>
                      <label htmlFor="document-name">
                        Nombre del documento <span className="req">*</span>
                      </label>
                      <input
                        id="document-name"
                        value={docName}
                        onChange={(e) => setDocName(e.target.value)}
                        placeholder="Ej: Certificado de nacimiento"
                        required
                      />
                    </div>
                    <div>
                      <label htmlFor="document-file">
                        Archivo <span className="req">*</span>
                      </label>
                      <input
                        key={docInputKey}
                        id="document-file"
                        type="file"
                        accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                        onChange={(e) => setDocFile(e.target.files?.[0] ?? null)}
                        required
                      />
                    </div>
                    <p className="muted small-text full" style={{ margin: 0 }}>
                      PDF, JPG o PNG, hasta 5 MB.
                    </p>
                  </div>
                  <div className="row-actions" style={{ justifyContent: "flex-start", marginTop: 10 }}>
                    <button className="btn small" disabled={dossierSaving}>
                      {dossierSaving ? "Subiendo..." : "Subir documento"}
                    </button>
                  </div>
                </form>

                {dossier.documents.length === 0 ? (
                  <p className="muted" style={{ marginTop: 16 }}>
                    Aún no hay documentos adjuntos.
                  </p>
                ) : (
                  <div className="table-wrap" style={{ marginTop: 16 }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Documento</th>
                          <th>Archivo</th>
                          <th>Subido</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {dossier.documents.map((document) => (
                          <tr key={document.id}>
                            <td>
                              <strong>{document.name}</strong>
                            </td>
                            <td>
                              {document.filename}
                              <div className="muted small-text">
                                {formatBytes(document.size)}
                              </div>
                            </td>
                            <td>{formatDate(document.uploaded_at)}</td>
                            <td>
                              <div className="row-actions">
                                <button
                                  className="btn small secondary"
                                  onClick={() =>
                                    downloadFile(
                                      `/admission-documents/${document.id}/download`,
                                      document.filename,
                                    ).catch((e) =>
                                      setDossierError(
                                        e instanceof Error
                                          ? e.message
                                          : "No se pudo descargar el documento",
                                      ),
                                    )
                                  }
                                >
                                  Descargar
                                </button>
                                <button
                                  className="btn small danger"
                                  onClick={() => removeDocument(document)}
                                >
                                  Eliminar
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ) : dossierTab === "entrevistas" ? (
              <>
                <form onSubmit={saveInterview}>
                  <div className="form-grid">
                    <div>
                      <label htmlFor="interview-date">
                        Fecha y hora <span className="req">*</span>
                      </label>
                      <input
                        id="interview-date"
                        type="datetime-local"
                        value={interviewForm.scheduled_at}
                        onChange={(e) =>
                          setInterviewForm({ ...interviewForm, scheduled_at: e.target.value })
                        }
                        required
                      />
                    </div>
                    <div>
                      <label htmlFor="interview-interviewer">
                        Entrevistador <span className="req">*</span>
                      </label>
                      <input
                        id="interview-interviewer"
                        value={interviewForm.interviewer}
                        onChange={(e) =>
                          setInterviewForm({ ...interviewForm, interviewer: e.target.value })
                        }
                        placeholder="Ej: Dirección, UTP..."
                        required
                      />
                    </div>
                    <div>
                      <label htmlFor="interview-mode">Modalidad</label>
                      <select
                        id="interview-mode"
                        value={interviewForm.mode}
                        onChange={(e) =>
                          setInterviewForm({
                            ...interviewForm,
                            mode: e.target.value as InterviewMode,
                          })
                        }
                      >
                        <option value="presencial">Presencial</option>
                        <option value="online">Online</option>
                        <option value="telefonica">Telefónica</option>
                      </select>
                    </div>
                    <div>
                      <label htmlFor="interview-status">Estado</label>
                      <select
                        id="interview-status"
                        value={interviewForm.status}
                        onChange={(e) =>
                          setInterviewForm({
                            ...interviewForm,
                            status: e.target.value as InterviewStatus,
                          })
                        }
                      >
                        <option value="pendiente">Pendiente</option>
                        <option value="realizada">Realizada</option>
                        <option value="cancelada">Cancelada</option>
                      </select>
                    </div>
                    <div className="full">
                      <label htmlFor="interview-notes">Observaciones</label>
                      <textarea
                        id="interview-notes"
                        rows={2}
                        value={interviewForm.notes}
                        onChange={(e) =>
                          setInterviewForm({ ...interviewForm, notes: e.target.value })
                        }
                      />
                    </div>
                  </div>
                  <div className="row-actions" style={{ justifyContent: "flex-start", marginTop: 10 }}>
                    <button className="btn small" disabled={dossierSaving}>
                      {dossierSaving
                        ? "Guardando..."
                        : interviewForm.id
                          ? "Guardar cambios"
                          : "Agendar entrevista"}
                    </button>
                    {interviewForm.id && (
                      <button
                        type="button"
                        className="btn small secondary"
                        onClick={() => setInterviewForm(emptyInterviewForm())}
                      >
                        Cancelar edición
                      </button>
                    )}
                  </div>
                </form>

                {dossier.interviews.length === 0 ? (
                  <p className="muted" style={{ marginTop: 16 }}>
                    Aún no hay entrevistas agendadas.
                  </p>
                ) : (
                  <div className="table-wrap" style={{ marginTop: 16 }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Fecha</th>
                          <th>Entrevistador</th>
                          <th>Modalidad</th>
                          <th>Estado</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {dossier.interviews.map((interview) => (
                          <tr key={interview.id}>
                            <td>{formatDateTime(interview.scheduled_at)}</td>
                            <td>
                              <strong>{interview.interviewer}</strong>
                              {interview.notes && (
                                <div className="muted small-text msg-cell">
                                  {interview.notes}
                                </div>
                              )}
                            </td>
                            <td>{INTERVIEW_MODE_LABELS[interview.mode]}</td>
                            <td>
                              <span
                                className={`badge ${interviewStatusTone(interview.status)}`}
                              >
                                {INTERVIEW_STATUS_LABELS[interview.status]}
                              </span>
                            </td>
                            <td>
                              <div className="row-actions">
                                <button
                                  className="btn small secondary"
                                  onClick={() => editInterview(interview)}
                                >
                                  Editar
                                </button>
                                <button
                                  className="btn small danger"
                                  onClick={() => removeInterview(interview)}
                                >
                                  Eliminar
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ) : (
              <>
                <form onSubmit={saveScore}>
                  <div className="form-grid">
                    <div>
                      <label htmlFor="score-criterion">
                        Criterio <span className="req">*</span>
                      </label>
                      <input
                        id="score-criterion"
                        value={scoreForm.criterion}
                        onChange={(e) =>
                          setScoreForm({ ...scoreForm, criterion: e.target.value })
                        }
                        placeholder="Ej: Prueba de admisión, entrevista..."
                        required
                      />
                    </div>
                    <div>
                      <label htmlFor="score-value">
                        Puntaje (0 a 100) <span className="req">*</span>
                      </label>
                      <input
                        id="score-value"
                        type="number"
                        min={0}
                        max={100}
                        step="0.1"
                        value={scoreForm.score}
                        onChange={(e) => setScoreForm({ ...scoreForm, score: e.target.value })}
                        required
                      />
                    </div>
                    <div>
                      <label htmlFor="score-weight">Ponderación</label>
                      <input
                        id="score-weight"
                        type="number"
                        min={1}
                        max={10}
                        value={scoreForm.weight}
                        onChange={(e) => setScoreForm({ ...scoreForm, weight: e.target.value })}
                        required
                      />
                    </div>
                    <div>
                      <label htmlFor="score-notes">Observaciones</label>
                      <input
                        id="score-notes"
                        value={scoreForm.notes}
                        onChange={(e) => setScoreForm({ ...scoreForm, notes: e.target.value })}
                      />
                    </div>
                  </div>
                  <div className="row-actions" style={{ justifyContent: "flex-start", marginTop: 10 }}>
                    <button className="btn small" disabled={dossierSaving}>
                      {dossierSaving
                        ? "Guardando..."
                        : scoreForm.id
                          ? "Guardar cambios"
                          : "Agregar puntaje"}
                    </button>
                    {scoreForm.id && (
                      <button
                        type="button"
                        className="btn small secondary"
                        onClick={() => setScoreForm(emptyScoreForm())}
                      >
                        Cancelar edición
                      </button>
                    )}
                  </div>
                </form>

                {dossier.scores.length === 0 ? (
                  <p className="muted" style={{ marginTop: 16 }}>
                    Aún no hay puntajes registrados.
                  </p>
                ) : (
                  <>
                    <div className="table-wrap" style={{ marginTop: 16 }}>
                      <table>
                        <thead>
                          <tr>
                            <th>Criterio</th>
                            <th>Puntaje</th>
                            <th>Ponderación</th>
                            <th>Observaciones</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {dossier.scores.map((score) => (
                            <tr key={score.id}>
                              <td>
                                <strong>{score.criterion}</strong>
                              </td>
                              <td>
                                <span className={`badge ${scoreTone(score.score)}`}>
                                  {score.score.toFixed(1)}
                                </span>
                              </td>
                              <td>{score.weight}</td>
                              <td className="muted small-text">{score.notes ?? "—"}</td>
                              <td>
                                <div className="row-actions">
                                  <button
                                    className="btn small secondary"
                                    onClick={() => editScore(score)}
                                  >
                                    Editar
                                  </button>
                                  <button
                                    className="btn small danger"
                                    onClick={() => removeScore(score)}
                                  >
                                    Eliminar
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p style={{ margin: "10px 0 0" }}>
                      Puntaje ponderado:{" "}
                      <strong>
                        {dossier.weighted_score == null
                          ? "—"
                          : dossier.weighted_score.toFixed(1)}
                      </strong>
                    </p>
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}


