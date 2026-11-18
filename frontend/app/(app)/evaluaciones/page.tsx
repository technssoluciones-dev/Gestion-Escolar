"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { formatDate, todayISO } from "@/lib/dates";
import {
  EVALUATION_KIND_LABELS,
  EVALUATION_KINDS,
  EvaluationKind,
} from "@/lib/evaluations";

type Course = { id: number; name: string; year: number };
type Subject = { id: number; name: string; code: string | null };
type CourseSubject = {
  id: number;
  course_id: number;
  subject_id: number;
  subject: Subject;
};
type Evaluation = {
  id: number;
  course_subject_id: number;
  course_id: number;
  course_name: string;
  subject_id: number;
  subject_name: string;
  teacher_name: string | null;
  title: string;
  kind: EvaluationKind;
  date: string;
  weight: number;
  grade_count: number;
};

type FormState = {
  id: number | null;
  courseId: string;
  courseSubjectId: string;
  title: string;
  kind: EvaluationKind;
  date: string;
  weight: string;
};

function emptyForm(): FormState {
  return {
    id: null,
    courseId: "",
    courseSubjectId: "",
    title: "",
    kind: "prueba",
    date: todayISO(),
    weight: "1",
  };
}

export default function EvaluacionesPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [assignments, setAssignments] = useState<CourseSubject[]>([]);
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [courseFilter, setCourseFilter] = useState("");
  const [subjectFilter, setSubjectFilter] = useState("");
  const [form, setForm] = useState<FormState | null>(null);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    setReady(false);
    Promise.all([
      api<{ items: Course[] }>("/courses?limit=200"),
      api<{ items: CourseSubject[] }>("/course-subjects?limit=200"),
      api<{ items: Evaluation[] }>("/evaluations?limit=200"),
    ])
      .then(([courseData, assignmentData, evaluationData]) => {
        setCourses(courseData.items);
        setAssignments(assignmentData.items);
        setEvaluations(evaluationData.items);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Error al cargar las evaluaciones"))
      .finally(() => setReady(true));
  }, [version]);

  const filterSubjects = useMemo(() => {
    const seen = new Set<number>();
    const list: Subject[] = [];
    for (const assignment of assignments) {
      if (courseFilter && String(assignment.course_id) !== courseFilter) continue;
      if (seen.has(assignment.subject_id)) continue;
      seen.add(assignment.subject_id);
      list.push(assignment.subject);
    }
    return list.sort((a, b) => a.name.localeCompare(b.name));
  }, [assignments, courseFilter]);

  const formSubjects = useMemo(() => {
    if (!form?.courseId) return [];
    return assignments
      .filter((assignment) => String(assignment.course_id) === form.courseId)
      .map((assignment) => assignment.subject)
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [assignments, form?.courseId]);

  const visible = useMemo(() => {
    const text = query.trim().toLowerCase();
    return evaluations.filter((evaluation) => {
      if (courseFilter && String(evaluation.course_id) !== courseFilter) return false;
      if (subjectFilter && String(evaluation.subject_id) !== subjectFilter) return false;
      if (!text) return true;
      return `${evaluation.title} ${evaluation.course_name} ${evaluation.subject_name}`
        .toLowerCase()
        .includes(text);
    });
  }, [evaluations, query, courseFilter, subjectFilter]);

  function openCreate() {
    setFormError("");
    setForm(emptyForm());
  }

  function openEdit(evaluation: Evaluation) {
    setFormError("");
    setForm({
      id: evaluation.id,
      courseId: String(evaluation.course_id),
      courseSubjectId: String(evaluation.course_subject_id),
      title: evaluation.title,
      kind: evaluation.kind,
      date: evaluation.date,
      weight: String(evaluation.weight),
    });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    setFormError("");
    setSaving(true);
    try {
      await api(form.id ? `/evaluations/${form.id}` : "/evaluations", {
        method: form.id ? "PUT" : "POST",
        body: {
          course_subject_id: Number(form.courseSubjectId),
          title: form.title,
          kind: form.kind,
          date: form.date,
          weight: Number(form.weight),
        },
      });
      setNotice(form.id ? "Evaluación actualizada." : "Evaluación creada.");
      setForm(null);
      setVersion((v) => v + 1);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "No se pudo guardar la evaluación");
    } finally {
      setSaving(false);
    }
  }

  async function remove(evaluation: Evaluation) {
    if (
      !window.confirm(
        `¿Eliminar la evaluación "${evaluation.title}" de ${evaluation.course_name}?`
      )
    )
      return;
    setError("");
    try {
      await api(`/evaluations/${evaluation.id}`, { method: "DELETE" });
      setNotice("Evaluación eliminada.");
      setVersion((v) => v + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo eliminar la evaluación");
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Evaluaciones</h1>
          <p>Define las pruebas, controles y trabajos de cada asignatura, con su fecha y ponderación.</p>
        </div>
        <button className="btn" onClick={openCreate}>
          + Nueva evaluación
        </button>
      </div>

      {error && <div className="alert">{error}</div>}
      {notice && <div className="notice">{notice}</div>}

      <div className="toolbar">
        <input
          placeholder="Buscar evaluación"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          value={courseFilter}
          onChange={(e) => {
            setCourseFilter(e.target.value);
            setSubjectFilter("");
          }}
        >
          <option value="">Todos los cursos</option>
          {courses.map((course) => (
            <option key={course.id} value={course.id}>
              {course.name} ({course.year})
            </option>
          ))}
        </select>
        <select value={subjectFilter} onChange={(e) => setSubjectFilter(e.target.value)}>
          <option value="">Todas las asignaturas</option>
          {filterSubjects.map((subject) => (
            <option key={subject.id} value={subject.id}>
              {subject.name}
            </option>
          ))}
        </select>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Evaluación</th>
              <th>Curso</th>
              <th>Asignatura</th>
              <th>Tipo</th>
              <th>Fecha</th>
              <th>Ponderación</th>
              <th>Notas</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((evaluation) => (
              <tr key={evaluation.id}>
                <td>
                  <strong>{evaluation.title}</strong>
                  {evaluation.teacher_name && (
                    <div className="muted small-text">{evaluation.teacher_name}</div>
                  )}
                </td>
                <td>{evaluation.course_name}</td>
                <td>{evaluation.subject_name}</td>
                <td>
                  <span className="badge info">{EVALUATION_KIND_LABELS[evaluation.kind]}</span>
                </td>
                <td>{formatDate(evaluation.date)}</td>
                <td>{evaluation.weight}</td>
                <td>
                  {evaluation.grade_count > 0 ? (
                    <span className="badge ok">{evaluation.grade_count}</span>
                  ) : (
                    <span className="badge none">0</span>
                  )}
                </td>
                <td>
                  <div className="row-actions">
                    <button className="btn secondary small" onClick={() => openEdit(evaluation)}>
                      Editar
                    </button>
                    <button
                      className="btn danger small"
                      onClick={() => remove(evaluation)}
                      disabled={evaluation.grade_count > 0}
                      title={
                        evaluation.grade_count > 0
                          ? "Tiene notas registradas; elimínalas primero"
                          : "Eliminar evaluación"
                      }
                    >
                      Eliminar
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {ready && visible.length === 0 && (
              <tr>
                <td colSpan={8} className="empty">
                  Aún no hay evaluaciones. Crea la primera para registrar sus notas desde Notas.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {form && (
        <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && setForm(null)}>
          <form className="modal" onSubmit={submit}>
            <div className="modal-head">
              <h2>{form.id ? "Editar evaluación" : "Nueva evaluación"}</h2>
              <button type="button" className="btn secondary small" onClick={() => setForm(null)}>
                ✕
              </button>
            </div>

            {formError && <div className="alert">{formError}</div>}

            <div className="form-grid">
              <div>
                <label htmlFor="eval-course">
                  Curso <span className="req">*</span>
                </label>
                <select
                  id="eval-course"
                  required
                  value={form.courseId}
                  onChange={(e) =>
                    setForm({ ...form, courseId: e.target.value, courseSubjectId: "" })
                  }
                >
                  <option value="">Selecciona un curso</option>
                  {courses.map((course) => (
                    <option key={course.id} value={course.id}>
                      {course.name} ({course.year})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="eval-subject">
                  Asignatura <span className="req">*</span>
                </label>
                <select
                  id="eval-subject"
                  required
                  value={form.courseSubjectId}
                  onChange={(e) => setForm({ ...form, courseSubjectId: e.target.value })}
                >
                  <option value="">Selecciona una asignatura</option>
                  {formSubjects.map((subject) => {
                    const assignment = assignments.find(
                      (a) =>
                        String(a.course_id) === form.courseId &&
                        a.subject_id === subject.id
                    );
                    return (
                      <option key={subject.id} value={assignment?.id ?? ""}>
                        {subject.name}
                      </option>
                    );
                  })}
                </select>
                {form.courseId && formSubjects.length === 0 && (
                  <p className="muted small-text" style={{ margin: "6px 0 0" }}>
                    Ese curso no tiene asignaturas. Asígnalas en Horarios.
                  </p>
                )}
              </div>
              <div className="full">
                <label htmlFor="eval-title">
                  Nombre <span className="req">*</span>
                </label>
                <input
                  id="eval-title"
                  required
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder="Ej: Prueba 1, Control de lectura..."
                />
              </div>
              <div>
                <label htmlFor="eval-kind">Tipo</label>
                <select
                  id="eval-kind"
                  value={form.kind}
                  onChange={(e) =>
                    setForm({ ...form, kind: e.target.value as EvaluationKind })
                  }
                >
                  {EVALUATION_KINDS.map((kind) => (
                    <option key={kind} value={kind}>
                      {EVALUATION_KIND_LABELS[kind]}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="eval-date">
                  Fecha <span className="req">*</span>
                </label>
                <input
                  id="eval-date"
                  type="date"
                  required
                  value={form.date}
                  onChange={(e) => setForm({ ...form, date: e.target.value })}
                />
              </div>
              <div>
                <label htmlFor="eval-weight">Ponderación</label>
                <input
                  id="eval-weight"
                  type="number"
                  min={1}
                  step={1}
                  required
                  value={form.weight}
                  onChange={(e) => setForm({ ...form, weight: e.target.value })}
                />
              </div>
            </div>

            <div className="modal-foot">
              <button type="button" className="btn secondary" onClick={() => setForm(null)}>
                Cancelar
              </button>
              <button className="btn" disabled={saving}>
                {saving ? "Guardando..." : "Guardar evaluación"}
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
