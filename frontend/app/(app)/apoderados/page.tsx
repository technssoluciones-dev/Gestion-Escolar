"use client";

import CrudPage from "@/components/CrudPage";
import { formatRut } from "@/lib/rut";

export default function ApoderadosPage() {
  return (
    <CrudPage
      title="Apoderados"
      subtitle="Contacto de las familias."
      singular="apoderado"
      endpoint="/guardians"
      columns={[
        { header: "RUT", render: (r) => formatRut(r.rut) },
        { header: "Nombre", render: (r) => <strong>{r.last_name}, {r.first_name}</strong> },
        { header: "Teléfono", render: (r) => r.phone ?? <span className="muted">—</span> },
        { header: "Correo", render: (r) => r.email ?? <span className="muted">—</span> },
      ]}
      fields={[
        { name: "rut", label: "RUT", type: "rut", required: true },
        { name: "phone", label: "Teléfono", type: "text" },
        { name: "first_name", label: "Nombres", type: "text", required: true },
        { name: "last_name", label: "Apellidos", type: "text", required: true },
        { name: "email", label: "Correo", type: "email", full: true },
        { name: "address", label: "Dirección", type: "text", full: true },
      ]}
    />
  );
}
