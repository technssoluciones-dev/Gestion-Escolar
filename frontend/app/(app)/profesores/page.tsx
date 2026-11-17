"use client";

import CrudPage from "@/components/CrudPage";
import { formatRut } from "@/lib/rut";

export default function ProfesoresPage() {
  return (
    <CrudPage
      title="Profesores"
      subtitle="Docentes del colegio y los cursos que tienen a cargo."
      singular="profesor"
      endpoint="/teachers"
      columns={[
        { header: "RUT", render: (r) => formatRut(r.rut) },
        { header: "Nombre", render: (r) => <strong>{r.last_name}, {r.first_name}</strong> },
        { header: "Especialidad", render: (r) => r.specialty ?? <span className="muted">—</span> },
        {
          header: "Profesor jefe de",
          render: (r) =>
            r.head_courses.length ? r.head_courses.map((c: any) => c.name).join(", ") : <span className="muted">—</span>,
        },
        {
          header: "Estado",
          render: (r) => (
            <span className={`badge ${r.is_active ? "ok" : "warn"}`}>{r.is_active ? "Activo" : "Inactivo"}</span>
          ),
        },
      ]}
      fields={[
        { name: "rut", label: "RUT", type: "rut", required: true },
        { name: "specialty", label: "Especialidad", type: "text" },
        { name: "first_name", label: "Nombres", type: "text", required: true },
        { name: "last_name", label: "Apellidos", type: "text", required: true },
        { name: "email", label: "Correo", type: "email" },
        { name: "phone", label: "Teléfono", type: "text" },
        { name: "hire_date", label: "Fecha de contratación", type: "date" },
        { name: "is_active", label: "Profesor activo", type: "checkbox", defaultValue: true },
      ]}
    />
  );
}
