"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDate, gradeClass, todayISO } from "@/lib/dates";
import { formatRut } from "@/lib/rut";

type Course = { id: number; name: string; year: number };
type Subject = { id: number; name: string; code: string | null };

type Grade = {
  id: number;
  student_id: number;
  subject_id: number;
  title: string;
  score: number;
  weight: number;
  date: string;
  evaluation_id: number | null;
};

type Evaluation = {
  id: number;
  title: string;
  kind: string;
  date: string;
  weight: number;
};

type Summary = {
  average: number | null;
  approved: number;
  failed: number;
  without_grades: number;
  grade_count: number;
};

type ReportRow = {
  student_id: number;
  full_name: string;
  rut: string;
  grades: Grade[];
  average: number | null;
  count: number;
};

type Report = {
  course: Course;
  subject: Subject;
  items: ReportRow[];
  summary: Summary;
};

type SubjectAverage = { subject_id: number; average: number | null; count: number };

type MatrixRow = {
  student_id: number;
  full_name: string;
  rut: string;
  averages: SubjectAverage[];
  overall: number | null;
};

type Matrix = {
  course: Course;
  subjects: Subject[];
  items: MatrixRow[];
  subject_averages: SubjectAverage[];
  summary: Summary;
};

function score(value: number | null | undefined): string {
  return value == null ? "—" : Number(value).toFixed(1);
}

export default function NotasPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [ready, setReady] = useState(false);
  const [courseId, setCourseId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [matrix, setMatrix] = useState<Matrix | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [version, setVersion] = useState(0);
  const [modal, setModal] = useState<{ mode: "bulk" } | { mode: "single"; row: ReportRow } | null>(null);

  useEffect(() => {
    Promise.all([
      api<{ items: Course[] }>("/courses?limit=200"),
      api<{ items: Subject[] }>("/subjects?limit=200"),
    ])
      .then(([courseData, subjectData]) => {
        setCourses(courseData.items);
        setSubjects(subjectData.items);
        if (courseData.items.length) setCourseId((prev) => prev || String(courseData.items[0].id));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Error al cargar los datos"))
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    if (!courseId) {
      setReport(null);
      setMatrix(null);
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    setReport(null);
    setMatrix(null);
    const path = subjectId
      ? `/grades/report?course_id=${courseId}&subject_id=${subjectId}`
      : `/grades/matrix?course_id=${courseId}`;
    api<Report | Matrix>(path)
      .then((data) => {
        if (subjectId) setReport(data as Report);
        else setMatrix(data as Matrix);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "No se pudieron cargar las notas"))
      .finally(() => setLoading(false));
  }, [courseId, subjectId, version]);

  const summary = report?.summary ?? matrix?.summary ?? null;
  const subject = subjects.find((s) => String(s.id) === subjectId);
  const course = courses.find((c) => String(c.id) === courseId);
  const students = (report?.items ?? matrix?.items ?? []).map((row) => ({
    student_id: row.student_id,
    full_name: row.full_name,
  }));

  async function removeGrade(grade: Grade) {
    if (!window.confirm(`¿Eliminar la nota "${grade.title}" (${score(grade.score)})?`)) return;
    try {
      await api(`/grades/${grade.id}`, { method: "DELETE" });
      setNotice("Nota eliminada.");
      setVersion((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo eliminar la nota");
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Notas</h1>
          <p>Escala chilena de 1.0 a 7.0, con promedio ponderado por asignatura.</p>
        </div>
        <button
          className="btn"
          disabled={!courseId || !subjectId}
          title={!subjectId ? "Elige una asignatura para registrar una evaluación" : undefined}
          onClick={() => setModal({ mode: "bulk" })}
        >
          + Registrar evaluación
        </button>
      </div>

      <div className="filters">
        <div>
          <label htmlFor="course">Curso</label>
          <select id="course" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
            <option value="">Selecciona un curso</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.year})
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="subject">Asignatura</label>
          <select id="subject" value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
            <option value="">Todas las asignaturas</option>
            {subjects.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        <div className="filters-actions">
          <span className="muted small-text">
            {subject
              ? "Vista de la asignatura"
              : "Vista general · elige una asignatura para registrar notas"}
          </span>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}
      {notice && <div className="notice">{notice}</div>}

      {ready && subjects.length === 0 && (
        <div className="empty-state">
          Aún no hay asignaturas. <Link href="/asignaturas">Crea la primera asignatura</Link> para
          registrar notas.
        </div>
      )}

      {ready && courses.length === 0 && (
        <div className="empty-state">
          Aún no hay cursos. <Link href="/cursos">Crea un curso</Link> para comenzar.
        </div>
      )}

      {summary && (
        <div className="cards">
          <div className="card">
            <div className="stat-label">Promedio general</div>
            <div className="stat-value">{score(summary.average)}</div>
          </div>
          <div className="card">
            <div className="stat-label">Aprobados (≥ 4.0)</div>
            <div className="stat-value">{summary.approved}</div>
          </div>
          <div className="card">
            <div className="stat-label">En riesgo (&lt; 4.0)</div>
            <div className="stat-value">{summary.failed}</div>
          </div>
          <div className="card">
            <div className="stat-label">Sin notas</div>
            <div className="stat-value">{summary.without_grades}</div>
          </div>
          <div className="card">
            <div className="stat-label">Notas registradas</div>
            <div className="stat-value">{summary.grade_count}</div>
          </div>
        </div>
      )}

      {loading && <p className="muted">Cargando notas...</p>}

      {!loading && report && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Estudiante</th>
                <th>Notas</th>
                <th>Promedio</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {report.items.map((row) => (
                <tr key={row.student_id}>
                  <td>
                    <strong>{row.full_name}</strong>
                    <div className="muted small-text">{formatRut(row.rut)}</div>
                  </td>
                  <td>
                    <div className="chips">
                      {row.grades.map((grade) => (
                        <span
                          key={grade.id}
                          className={`chip ${gradeClass(grade.score)}`}
                          title={`${grade.title} · ${formatDate(grade.date)} · Ponderación ${grade.weight}`}
                        >
                          <span className="chip-title">{grade.title}</span>
                          <strong>{score(grade.score)}</strong>
                          <button
                            type="button"
                            className="chip-x"
                            aria-label={`Eliminar ${grade.title}`}
                            onClick={() => removeGrade(grade)}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                      {row.grades.length === 0 && <span className="muted small-text">Sin notas</span>}
                    </div>
                  </td>
                  <td>
                    <span className={`grade ${gradeClass(row.average)}`}>{score(row.average)}</span>
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        className="btn secondary small"
                        onClick={() => setModal({ mode: "single", row })}
                      >
                        + Nota
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {report.items.length === 0 && (
            <div className="empty">
              {course?.name} no tiene estudiantes activos.{" "}
              <Link href="/estudiantes">Asigna estudiantes al curso</Link>.
            </div>
          )}
        </div>
      )}

      {!loading && matrix && (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Estudiante</th>
                  {matrix.subjects.map((s) => (
                    <th key={s.id}>{s.name}</th>
                  ))}
                  <th>Promedio general</th>
                </tr>
              </thead>
              <tbody>
                {matrix.items.map((row) => (
                  <tr key={row.student_id}>
                    <td>
                      <strong>{row.full_name}</strong>
                      <div className="muted small-text">{formatRut(row.rut)}</div>
                    </td>
                    {matrix.subjects.map((s) => {
                      const average = row.averages.find((a) => a.subject_id === s.id)?.average ?? null;
                      return (
                        <td key={s.id}>
                          <span className={`grade ${gradeClass(average)}`}>{score(average)}</span>
                        </td>
                      );
                    })}
                    <td>
                      <span className={`grade ${gradeClass(row.overall)}`}>{score(row.overall)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
              {matrix.items.length > 0 && matrix.subjects.length > 0 && (
                <tfoot>
                  <tr>
                    <th>Promedio del curso</th>
                    {matrix.subjects.map((s) => {
                      const average =
                        matrix.subject_averages.find((a) => a.subject_id === s.id)?.average ?? null;
                      return (
                        <th key={s.id}>
                          <span className={`grade ${gradeClass(average)}`}>{score(average)}</span>
                        </th>
                      );
                    })}
                    <th>
                      <span className={`grade ${gradeClass(matrix.summary.average)}`}>
                        {score(matrix.summary.average)}
                      </span>
                    </th>
                  </tr>
                </tfoot>
              )}
            </table>
            {matrix.subjects.length === 0 && (
              <div className="empty">
                Este curso todavía no tiene notas. Elige una asignatura y usa &quot;Registrar
                evaluación&quot; para comenzar.
              </div>
            )}
            {matrix.subjects.length > 0 && matrix.items.length === 0 && (
              <div className="empty">
                {course?.name} no tiene estudiantes activos.{" "}
                <Link href="/estudiantes">Asigna estudiantes al curso</Link>.
              </div>
            )}
          </div>
          <p className="muted small-text" style={{ marginTop: 10 }}>
            Cada celda muestra el promedio ponderado del estudiante en esa asignatura. Las notas se
            registran con un mínimo de 1.0 y un máximo de 7.0.
          </p>
        </>
      )}

      {modal?.mode === "bulk" && courseId && subjectId && (
        <BulkModal
          courseName={course?.name ?? ""}
          subjectName={subject?.name ?? ""}
          courseId={Number(courseId)}
          subjectId={Number(subjectId)}
          students={students}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null);
            setNotice("Evaluación registrada.");
            setVersion((v) => v + 1);
          }}
        />
      )}

      {modal?.mode === "single" && subjectId && (
        <SingleModal
          row={modal.row}
          subjectId={Number(subjectId)}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null);
            setNotice("Nota registrada.");
            setVersion((v) => v + 1);
          }}
        />
      )}
    </>
  );
}

function BulkModal(props: {
  courseName: string;
  subjectName: string;
  courseId: number;
  subjectId: number;
  students: { student_id: number; full_name: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState("Evaluación");
  const [date, setDate] = useState(todayISO());
  const [weight, setWeight] = useState("1");
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [evaluationId, setEvaluationId] = useState("");
  const [scores, setScores] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api<{ items: Evaluation[] }>(
      `/evaluations?course_id=${props.courseId}&subject_id=${props.subjectId}&limit=200`
    )
      .then((data) => setEvaluations(data.items))
      .catch(() => setEvaluations([]));
  }, [props.courseId, props.subjectId]);

  function selectEvaluation(value: string) {
    setEvaluationId(value);
    const evaluation = evaluations.find((e) => String(e.id) === value);
    if (evaluation) {
      setTitle(evaluation.title);
      setDate(evaluation.date);
      setWeight(String(evaluation.weight));
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");

    const items: { student_id: number; score: number }[] = [];
    for (const student of props.students) {
      const raw = (scores[student.student_id] ?? "").trim();
      if (!raw) continue;
      const value = Number(raw);
      if (Number.isNaN(value) || value < 1 || value > 7) {
        setError(`La nota de ${student.full_name} debe estar entre 1.0 y 7.0.`);
        return;
      }
      items.push({ student_id: student.student_id, score: value });
    }
    if (items.length === 0) {
      setError("Ingresa al menos una nota.");
      return;
    }

    setSaving(true);
    try {
      await api("/grades/bulk", {
        method: "POST",
        body: {
          course_id: props.courseId,
          subject_id: props.subjectId,
          title,
          date,
          weight: Number(weight),
          evaluation_id: evaluationId ? Number(evaluationId) : undefined,
          items,
        },
      });
      props.onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar la evaluación");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && props.onClose()}>
      <form className="modal wide" onSubmit={submit}>
        <div className="modal-head">
          <div>
            <h2>Registrar evaluación</h2>
            <p className="muted small-text" style={{ margin: 0 }}>
              {props.courseName} · {props.subjectName}
            </p>
          </div>
          <button type="button" className="btn secondary small" onClick={props.onClose}>
            ✕
          </button>
        </div>

        {error && <div className="alert">{error}</div>}

        <div className="form-grid">
          <div className="full">
            <label htmlFor="bulk-evaluation">Evaluación formal</label>
            <select
              id="bulk-evaluation"
              value={evaluationId}
              onChange={(e) => selectEvaluation(e.target.value)}
            >
              <option value="">Sin evaluación (registro libre)</option>
              {evaluations.map((evaluation) => (
                <option key={evaluation.id} value={evaluation.id}>
                  {evaluation.title} · {formatDate(evaluation.date)} · ponderación {evaluation.weight}
                </option>
              ))}
            </select>
            <p className="muted small-text" style={{ margin: "6px 0 0" }}>
              {evaluations.length === 0
                ? "Este curso y asignatura aún no tienen evaluaciones definidas."
                : "Al elegir una evaluación, su nombre, fecha y ponderación se usan automáticamente."}{" "}
              <Link href="/evaluaciones">Administrar evaluaciones</Link>.
            </p>
          </div>
          <div className="full">
            <label htmlFor="bulk-title">Nombre de la evaluación</label>
            <input
              id="bulk-title"
              required
              disabled={!!evaluationId}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ej: Prueba 1, Control de lectura..."
            />
          </div>
          <div>
            <label htmlFor="bulk-date">Fecha</label>
            <input
              id="bulk-date"
              type="date"
              required
              disabled={!!evaluationId}
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="bulk-weight">Ponderación</label>
            <input
              id="bulk-weight"
              type="number"
              min={1}
              step={1}
              required
              disabled={!!evaluationId}
              value={weight}
              onChange={(e) => setWeight(e.target.value)}
            />
          </div>
        </div>

        <label style={{ marginTop: 16 }}>
          Notas (deja en blanco a quienes no rindieron la evaluación)
        </label>
        <div className="score-grid">
          {props.students.map((student) => (
            <div className="score-row" key={student.student_id}>
              <span>{student.full_name}</span>
              <input
                type="number"
                min={1}
                max={7}
                step={0.1}
                placeholder="—"
                value={scores[student.student_id] ?? ""}
                onChange={(e) => setScores((prev) => ({ ...prev, [student.student_id]: e.target.value }))}
              />
            </div>
          ))}
          {props.students.length === 0 && <span className="muted">El curso no tiene estudiantes.</span>}
        </div>

        <div className="modal-foot">
          <button type="button" className="btn secondary" onClick={props.onClose}>
            Cancelar
          </button>
          <button className="btn" disabled={saving || props.students.length === 0}>
            {saving ? "Guardando..." : "Guardar evaluación"}
          </button>
        </div>
      </form>
    </div>
  );
}

function SingleModal(props: {
  row: ReportRow;
  subjectId: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(`Nota ${props.row.count + 1}`);
  const [value, setValue] = useState("");
  const [date, setDate] = useState(todayISO());
  const [weight, setWeight] = useState("1");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    const numeric = Number(value);
    if (Number.isNaN(numeric) || numeric < 1 || numeric > 7) {
      setError("La nota debe estar entre 1.0 y 7.0.");
      return;
    }

    setSaving(true);
    try {
      await api("/grades", {
        method: "POST",
        body: {
          student_id: props.row.student_id,
          subject_id: props.subjectId,
          title,
          score: numeric,
          date,
          weight: Number(weight),
        },
      });
      props.onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar la nota");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && props.onClose()}>
      <form className="modal" onSubmit={submit}>
        <div className="modal-head">
          <div>
            <h2>Nueva nota</h2>
            <p className="muted small-text" style={{ margin: 0 }}>
              {props.row.full_name}
            </p>
          </div>
          <button type="button" className="btn secondary small" onClick={props.onClose}>
            ✕
          </button>
        </div>

        {error && <div className="alert">{error}</div>}

        <div className="form-grid">
          <div className="full">
            <label htmlFor="single-title">Evaluación</label>
            <input
              id="single-title"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="single-score">Nota (1.0 a 7.0)</label>
            <input
              id="single-score"
              type="number"
              min={1}
              max={7}
              step={0.1}
              required
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="single-date">Fecha</label>
            <input id="single-date" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div>
            <label htmlFor="single-weight">Ponderación</label>
            <input
              id="single-weight"
              type="number"
              min={1}
              step={1}
              required
              value={weight}
              onChange={(e) => setWeight(e.target.value)}
            />
          </div>
        </div>

        <div className="modal-foot">
          <button type="button" className="btn secondary" onClick={props.onClose}>
            Cancelar
          </button>
          <button className="btn" disabled={saving}>
            {saving ? "Guardando..." : "Guardar nota"}
          </button>
        </div>
      </form>
    </div>
  );
}
