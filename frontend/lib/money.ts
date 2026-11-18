export function formatCLP(value: number): string {
  return new Intl.NumberFormat("es-CL", {
    style: "currency",
    currency: "CLP",
    maximumFractionDigits: 0,
  }).format(value);
}

export const CONCEPT_LABELS: Record<string, string> = {
  matricula: "Matrícula",
  mensualidad: "Mensualidad",
  cuota: "Cuota",
  otro: "Otro",
};

export const FEE_STATUS_LABELS: Record<string, string> = {
  pendiente: "Pendiente",
  parcial: "Parcial",
  pagada: "Pagada",
  vencida: "Vencida",
};

export const PAYMENT_METHOD_LABELS: Record<string, string> = {
  efectivo: "Efectivo",
  transferencia: "Transferencia",
  tarjeta: "Tarjeta",
  cheque: "Cheque",
  otro: "Otro",
};

export function feeStatusTone(status: string): string {
  if (status === "pagada") return "ok";
  if (status === "parcial") return "warn";
  if (status === "vencida") return "bad";
  return "info";
}
