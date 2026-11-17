"use client";

import CrudPage from "@/components/CrudPage";
import { formatRut } from "@/lib/rut";

const courseLabel = (c: any) => `${c.name} (${c.year})`;

export default function EstudiantesPage() {
  return (
    <CrudPage
      title="Estudiantes"
      subtitle="Matrícula, curso y apoderado de cada estudiante."
      singular="estudiante"
      endpoint="/students"
      deleteMessage="¿Retirar a este estudiante? Su ficha se conserva, pero dejará de aparecer en las listas."
      filter={{ param: "course_id", label: "Todos los cursos", optionsFrom: { path: "/courses", label: courseLabel } }}
      columns={[
        { header: "RUT", render: (r) => formatRut(r.rut) },
        { header: "Nombre", render: (r) => <strong>{r.last_name}, {r.first_name}</strong> },
        { header: "Curso", render: (r) => r.course?.name ?? <span className="muted">Sin curso</span> },
        { header: "Apoderado", render: (r) => r.guardian?.full_name ?? <span className="muted">—</span> },
        {
          header: "Estado",
          render: (r) => <span className={`badge ${r.status === "activo" ? "ok" : "warn"}`}>{r.status}</span>,
        },
      ]}
      fields={[
        { name: "rut", label: "RUT", type: "rut", required: true },
        { name: "birth_date", label: "Fecha de nacimiento", type: "date", required: true },
        { name: "first_name", label: "Nombres", type: "text", required: true },
        { name: "last_name", label: "Apellidos", type: "text", required: true },
        {
          name: "gender",
          label: "Género",
          type: "select",
          options: [
            { value: "F", label: "Femenino" },
            { value: "M", label: "Masculino" },
            { value: "O", label: "Otro" },
          ],
        },
        { name: "email", label: "Correo", type: "email" },
        { name: "address", label: "Dirección", type: "text", full: true },
        { name: "enrollment_date", label: "Fecha de matrícula", type: "date" },
        {
          name: "status",
          label: "Estado",
          type: "select",
          required: true,
          defaultValue: "activo",
          options: [
            { value: "activo", label: "Activo" },
            { value: "retirado", label: "Retirado" },
          ],
        },
        { name: "course_id", label: "Curso", type: "select", optionsFrom: { path: "/courses", label: courseLabel } },
        {
          name: "guardian_id",
          label: "Apoderado",
          type: "select",
          optionsFrom: { path: "/guardians", label: (g) => `${g.full_name} · ${formatRut(g.rut)}` },
        },
      ]}
    />
  );
}
