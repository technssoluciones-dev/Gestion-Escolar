"use client";

import CrudPage from "@/components/CrudPage";

const thisYear = new Date().getFullYear();

export default function CursosPage() {
  return (
    <CrudPage
      title="Cursos"
      subtitle="Cursos del año, su profesor jefe y cuántos estudiantes tienen."
      singular="curso"
      endpoint="/courses"
      searchable={false}
      deleteMessage="¿Eliminar este curso? Sus estudiantes quedarán sin curso asignado."
      columns={[
        { header: "Año", render: (r) => r.year },
        { header: "Curso", render: (r) => <strong>{r.name}</strong> },
        { header: "Nivel", render: (r) => r.level },
        { header: "Profesor jefe", render: (r) => r.head_teacher_name ?? <span className="muted">Sin asignar</span> },
        {
          header: "Estudiantes",
          render: (r) => (
            <span className={`badge ${r.student_count > r.capacity ? "warn" : "ok"}`}>
              {r.student_count} / {r.capacity}
            </span>
          ),
        },
      ]}
      fields={[
        { name: "name", label: "Nombre del curso", type: "text", required: true },
        { name: "year", label: "Año", type: "number", required: true, defaultValue: thisYear },
        {
          name: "level",
          label: "Nivel",
          type: "select",
          required: true,
          defaultValue: "Básica",
          options: [
            { value: "Parvularia", label: "Parvularia" },
            { value: "Básica", label: "Básica" },
            { value: "Media", label: "Media" },
          ],
        },
        { name: "capacity", label: "Capacidad", type: "number", required: true, defaultValue: 45 },
        {
          name: "head_teacher_id",
          label: "Profesor jefe",
          type: "select",
          full: true,
          optionsFrom: { path: "/teachers", label: (t) => `${t.full_name}${t.specialty ? " · " + t.specialty : ""}` },
        },
      ]}
    />
  );
}
