"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Dashboard = {
  students: number;
  teachers: number;
  guardians: number;
  courses: number;
  students_without_course: number;
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
  const stats = [
    { label: "Estudiantes activos", value: data.students },
    { label: "Profesores", value: data.teachers },
    { label: "Apoderados", value: data.guardians },
    { label: "Cursos", value: data.courses },
  ];

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
    </>
  );
}
