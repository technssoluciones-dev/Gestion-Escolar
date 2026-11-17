/** Utilidades para el RUT chileno (mismo cálculo que el backend). */

function calcDv(body: string): string {
  let total = 0;
  let factor = 2;
  for (const digit of body.split("").reverse()) {
    total += Number(digit) * factor;
    factor = factor === 7 ? 2 : factor + 1;
  }
  const result = 11 - (total % 11);
  if (result === 11) return "0";
  if (result === 10) return "K";
  return String(result);
}

function clean(value: string): string {
  return (value || "").replace(/[^0-9kK]/g, "").toUpperCase();
}

export function isValidRut(value: string): boolean {
  const c = clean(value);
  if (c.length < 7 || c.length > 9) return false;
  const body = c.slice(0, -1);
  if (!/^\d+$/.test(body)) return false;
  return calcDv(body) === c.slice(-1);
}

/** '123456785' o '12345678-5' -> '12.345.678-5'. Si no se puede, lo devuelve igual. */
export function formatRut(value: string): string {
  const c = clean(value);
  if (c.length < 2) return value;
  const body = c.slice(0, -1).replace(/^0+/, "");
  const withDots = body.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${withDots}-${c.slice(-1)}`;
}
