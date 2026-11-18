"use client";

import CrudPage from "@/components/CrudPage";

export default function AsignaturasPage() {
  return (
    <CrudPage
      title="Asignaturas"
      subtitle="Ramos que se dictan en el colegio. Cada nota se asocia a una asignatura."
      singular="asignatura"
      endpoint="/subjects"
      searchPlaceholder="Buscar asignatura..."
      deleteMessage="¿Eliminar esta asignatura? Solo es posible si no tiene notas registradas."
      columns={[
        { header: "Asignatura", render: (r) => <strong>{r.name}</strong> },
        { header: "Código", render: (r) => r.code ?? <span className="muted">—</span> },
      ]}
      fields={[
        { name: "name", label: "Nombre", type: "text", required: true },
        { name: "code", label: "Código", type: "text" },
      ]}
    />
  );
}
