/** Utilidades de fecha para los formularios (siempre en hora local del navegador). */

export function todayISO(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

export function monthISO(): string {
  return todayISO().slice(0, 7);
}

/** Primer y último día de un mes "AAAA-MM". */
export function monthRange(month: string): { from: string; to: string } {
  const [year, monthNumber] = month.split("-").map(Number);
  const lastDay = new Date(year, monthNumber, 0).getDate();
  return {
    from: `${month}-01`,
    to: `${month}-${String(lastDay).padStart(2, "0")}`,
  };
}

/** "2026-11-17" -> "17-11-2026" */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${day}-${month}-${year}`;
}

/** Clase de color según una nota o un porcentaje. */
export function gradeClass(value: number | null | undefined): "ok" | "warn" | "bad" | "none" {
  if (value == null) return "none";
  if (value >= 5) return "ok";
  if (value >= 4) return "warn";
  return "bad";
}
