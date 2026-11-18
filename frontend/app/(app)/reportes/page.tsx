"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, API_URL, clearToken, getToken } from "@/lib/api";

type Course = { id: number; name: string; year: number };
type Subject = { id: number; name: string };
type CourseSubject = {
  id: number;
  course_id: number;
  subject_id: number;
  subject: Subject;
};
type Student = { id: number; full_name: string; rut: string };
type Me = { role: "admin" | "secretaria" | "profesor" | "apoderado" | "estudiante" };

function errorMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  return "No se pudo generar el reporte";
}

export default function ReportesPage() {
  const router = useRouter();
  const [courses, setCourses] = useState<Course[]>([]);
  const [assignments, setAssignments] = useState<CourseSubject[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [me, setMe] = useState<Me | null>(null);
  const [courseId, setCourseId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [studentId, setStudentId] = useState("");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    Promise.all([
      api<{ items: Course[] }>("/courses?limit=200"),
      api<{ items: CourseSubject[] }>("/course-subjects?limit=200"),
      api<Me>("/auth/me"),
    ])
      .then(([courseData, assignmentData, user]) => {
        setCourses(courseData.items);
        setAssignments(assignmentData.items);
        setMe(user);
        if (courseData.items.length > 0) setCourseId(String(courseData.items[0].id));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Error al cargar los reportes"))
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    setSubjectId("");
    setStudentId("");
    setStudents([]);
    if (!courseId) return;
    api<{ items: Student[] }>(`/students?course_id=${courseId}&limit=200`)
      .then((data) => setStudents(data.items))
      .catch((e) => setError(e instanceof Error ? e.message : "Error al cargar los estudiantes"));
  }, [courseId]);

  const course = courses.find((c) => String(c.id) === courseId) ?? null;

  const subjects = useMemo(() => {
    const seen = new Set<number>();
    const list: Subject[] = [];
    for (const assignment of assignments) {
      if (String(assignment.course_id) !== courseId) continue;
      if (seen.has(assignment.subject_id)) continue;
      seen.add(assignment.subject_id);
      list.push(assignment.subject);
    }
    return list.sort((a, b) => a.name.localeCompare(b.name));
  }, [assignments, courseId]);

  async function download(path: string, fallback: string, key: string) {
    setBusy(key);
    setError("");
    setNotice("");
    try {
      const token = getToken();
      const response = await fetch(`${API_URL}${path}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (response.status === 401) {
        clearToken();
        window.location.href = "/login";
        return;
      }
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(errorMessage(data?.detail));
      }
      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") ?? "";
      const match = /filename="?([^";]+)"?/.exec(disposition);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = match?.[1] ?? fallback;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setNotice(`Reporte descargado: ${match?.[1] ?? fallback}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo generar el reporte");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Reportes</h1>
          <p>Descarga planillas del curso en Excel o genera el certificado de alumno regular.</p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}
      {notice && <div className="notice">{notice}</div>}

      <div className="toolbar">
        <select value={courseId} onChange={(e) => setCourseId(e.target.value)}>
          <option value="">Selecciona un curso</option>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.year})
            </option>
          ))}
        </select>
        {ready && courses.length === 0 && (
          <span className="muted small-text">Primero crea un curso en la sección Cursos.</span>
        )}
      </div>

      <div className="grid-2">
        <section className="card report-card">
          <h2>Planilla de notas</h2>
          <p>
            Un libro Excel con una hoja por asignatura: evaluaciones, notas y promedio ponderado
            de cada estudiante.
          </p>
          <div className="report-fields">
            <select value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
              <option value="">Todas las asignaturas</option>
              {subjects.map((subject) => (
                <option key={subject.id} value={subject.id}>
                  {subject.name}
                </option>
              ))}
            </select>
          </div>
          <button
            className="btn"
            disabled={!course || busy !== ""}
            onClick={() =>
              download(
                `/reports/courses/${courseId}/grades.xlsx${subjectId ? `?subject_id=${subjectId}` : ""}`,
                "planilla-notas.xlsx",
                "grades",
              )
            }
          >
            {busy === "grades" ? "Generando..." : "Descargar Excel"}
          </button>
        </section>

        <section className="card report-card">
          <h2>Libro de asistencia</h2>
          <p>
            Un casillero por día del mes, con presentes, ausencias, atrasos y el porcentaje de
            asistencia de cada estudiante.
          </p>
          <div className="report-fields">
            <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
          </div>
          <button
            className="btn"
            disabled={!course || !month || busy !== ""}
            onClick={() =>
              download(
                `/reports/courses/${courseId}/attendance.xlsx?month=${month}`,
                "asistencia.xlsx",
                "attendance",
              )
            }
          >
            {busy === "attendance" ? "Generando..." : "Descargar Excel"}
          </button>
        </section>

        {me && (me.role === "admin" || me.role === "secretaria") && (
          <section className="card report-card">
            <h2>Resumen del curso</h2>
            <p>
              Una vista completa: promedio por asignatura, promedio general, asistencia anual,
              deuda total y deuda vencida de cada estudiante.
            </p>
            <button
              className="btn"
              disabled={!course || busy !== ""}
              onClick={() =>
                download(
                  `/reports/courses/${courseId}/summary.xlsx`,
                  "resumen-curso.xlsx",
                  "summary",
                )
              }
            >
              {busy === "summary" ? "Generando..." : "Descargar Excel"}
            </button>
          </section>
        )}

        <section className="card report-card">
          <h2>Certificado de alumno regular</h2>
          <p>
            Una hoja con los datos del estudiante, su curso, asistencia y promedio, lista para
            imprimir o guardar como PDF.
          </p>
          <div className="report-fields">
            <select value={studentId} onChange={(e) => setStudentId(e.target.value)}>
              <option value="">Selecciona un estudiante</option>
              {students.map((student) => (
                <option key={student.id} value={student.id}>
                  {student.full_name} · {student.rut}
                </option>
              ))}
            </select>
          </div>
          <button
            className="btn secondary"
            disabled={!studentId}
            onClick={() => router.push(`/reportes/certificado/${studentId}`)}
          >
            Ver certificado
          </button>
        </section>
      </div>

      <p className="muted small-text">
        Los reportes usan el año del curso para asistencia y deudas. La deuda considera los cobros
        del período del año en curso.
      </p>
    </>
  );
}
