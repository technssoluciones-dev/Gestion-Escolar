"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/dates";
import { formatCLP } from "@/lib/money";

type Dashboard = {
  students: number;
  teachers: number;
  guardians: number;
  courses: number;
  subjects: number;
  pending_admissions: number;
  students_without_course: number;
  fees_pending: number;
  fees_overdue: number;
  attendance_today: {
    date: string;
    marked: number;
    presente: number;
    ausente: number;
    atrasado: number;
    justificado: number;
    unmarked: number;
    rate: number | null;
  };
  per_course: { course: string; students: number }[];
};

export default function PanelPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Dashboard>("/dashboard")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="alert">{error}</div>;
  if (!data) return <p className="muted">Cargando...</p>;

  const max = Math.max(1, ...data.per_course.map((c) => c.students));
  const stats: { label: string; value: string | number }[] = [
    { label: "Estudiantes activos", value: data.students },
    { label: "Profesores", value: data.teachers },
    { label: "Apoderados", value: data.guardians },
    { label: "Cursos", value: data.courses },
    { label: "Asignaturas", value: data.subjects },
    { label: "Postulaciones pendientes", value: data.pending_admissions },
  ];
  if (data.fees_pending > 0 || data.fees_overdue > 0) {
    stats.push({ label: "Saldo por cobrar", value: formatCLP(data.fees_pending) });
    stats.push({ label: "Saldo vencido", value: formatCLP(data.fees_overdue) });
  }
  const attendance = data.attendance_today;
  const attended = attendance.presente + attendance.atrasado;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Panel</h1>
          <p>Resumen general del colegio.</p>
        </div>
      </div>

      <div className="cards">
        {stats.map((s) => (
          <div className="card" key={s.label}>
            <div className="stat-label">{s.label}</div>
            <div className="stat-value">{s.value}</div>
          </div>
        ))}
      </div>

      <div className="grid-2">
        <div className="card">
          <h2>Asistencia de hoy</h2>
          <p className="muted small-text" style={{ marginTop: -6 }}>
            {formatDate(attendance.date)}
          </p>
          {attendance.rate == null ? (
            <p className="muted">Aún no se registra asistencia hoy.</p>
          ) : (
            <>
              <div className="stat-value">{attendance.rate}%</div>
              <div className="bar-track" style={{ margin: "10px 0 8px" }}>
                <div className="bar-fill" style={{ width: `${attendance.rate}%` }} />
              </div>
              <p className="muted small-text">
                {attended} de {attendance.marked} estudiantes marcados · {attendance.unmarked} sin marcar
              </p>
            </>
          )}
          <Link href="/asistencia" className="btn secondary small" style={{ display: "inline-block" }}>
            Ir a asistencia
          </Link>
        </div>

        <div className="card">
          <h2>Estudiantes por curso</h2>
          {data.per_course.length === 0 && <p className="muted">Aún no hay cursos creados.</p>}
          {data.per_course.map((c) => (
            <div className="bar-row" key={c.course}>
              <span>{c.course}</span>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${(c.students / max) * 100}%` }} />
              </div>
              <span className="bar-num">{c.students}</span>
            </div>
          ))}
          {data.students_without_course > 0 && (
            <p className="muted" style={{ marginTop: 16 }}>
              {data.students_without_course} estudiante(s) sin curso asignado.
            </p>
          )}
        </div>
      </div>
    </>
  );
}
