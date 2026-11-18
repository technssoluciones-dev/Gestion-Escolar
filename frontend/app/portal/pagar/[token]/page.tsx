"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/dates";
import { CONCEPT_LABELS, formatCLP } from "@/lib/money";

type Intent = {
  token: string;
  status: "pendiente" | "pagada" | "cancelada";
  amount: number;
  provider: string;
  student_name: string;
  student_rut: string;
  course_name: string | null;
  concept: string;
  description: string | null;
  period: string;
  due_date: string;
  fee_amount: number;
  fee_paid: number;
  fee_balance: number;
  fee_status: string;
  paid_at: string | null;
  payment_id: number | null;
};

export default function CheckoutPage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const [webpayResult, setWebpayResult] = useState<string | null>(null);
  const token = params.token;
  const [intent, setIntent] = useState<Intent | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setWebpayResult(new URLSearchParams(window.location.search).get("webpay"));
  }, []);

  useEffect(() => {
    api<Intent>(`/payments/intents/${token}`)
      .then(setIntent)
      .catch((e) => setError(e instanceof Error ? e.message : "No se pudo cargar el pago"))
      .finally(() => setLoading(false));
  }, [token]);

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      setIntent(
        await api<Intent>(`/payments/intents/${token}/confirm`, { method: "POST" }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo confirmar el pago");
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    setBusy(true);
    setError("");
    try {
      await api<Intent>(`/payments/intents/${token}/cancel`, { method: "POST" });
      router.push("/portal");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cancelar el pago");
      setBusy(false);
    }
  }

  if (loading) return <p className="muted">Cargando pago...</p>;
  if (!intent) {
    return (
      <>
        <div className="alert">{error || "Pago no encontrado"}</div>
        <Link className="btn secondary" href="/portal">
          Volver al portal
        </Link>
      </>
    );
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Pago en línea</h1>
          <p>Revisa el cobro y confirma el pago.</p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}
      {webpayResult === "cancelado" && (
        <div className="alert">Cancelaste el pago en Webpay. No se registró ningún abono.</div>
      )}
      {(webpayResult === "rechazado" || webpayResult === "error") && (
        <div className="alert">
          Webpay no pudo completar el pago. Puedes intentarlo nuevamente desde el portal.
        </div>
      )}

      {intent.status === "pagada" ? (
        <div className="card">
          <h2>Pago confirmado</h2>
          <p>
            Registramos un abono de <strong>{formatCLP(intent.amount)}</strong> al cobro de{" "}
            {intent.student_name}. El comprobante quedó en la sección de pagos del colegio.
          </p>
          <p className="muted small-text">
            {intent.provider === "webpay"
              ? "Pago procesado por Webpay Plus"
              : `Referencia de la transacción: ONLINE-${intent.token.slice(0, 10).toUpperCase()}`}
            {intent.payment_id ? ` · Pago #${intent.payment_id}` : ""}
          </p>
          <Link className="btn" href="/portal">
            Volver al portal
          </Link>
        </div>
      ) : intent.status === "cancelada" ? (
        <div className="card">
          <h2>Pago cancelado</h2>
          <p>Este pago ya no está disponible. Puedes iniciar uno nuevo desde el portal.</p>
          <Link className="btn" href="/portal">
            Volver al portal
          </Link>
        </div>
      ) : (
        <div className="card">
          {intent.provider === "webpay" ? (
            <>
              <div className="notice">
                Este pago se completa en Webpay. Si cerraste la ventana sin terminar, inicia un
                nuevo pago desde el portal.
              </div>
              <Link className="btn" href="/portal" style={{ marginTop: 14 }}>
                Volver al portal
              </Link>
            </>
          ) : (
            <>
              <div className="notice">
                Pasarela de prueba: el pago se simula en el sistema. No se cobra dinero real.
              </div>
              <div className="table-wrap" style={{ marginTop: 14 }}>
                <table>
                  <tbody>
                    <tr>
                      <th>Estudiante</th>
                      <td>
                        {intent.student_name}
                        <div className="muted small-text">
                          {intent.student_rut}
                          {intent.course_name ? ` · ${intent.course_name}` : ""}
                        </div>
                      </td>
                    </tr>
                    <tr>
                      <th>Cobro</th>
                      <td>
                        {CONCEPT_LABELS[intent.concept] ?? intent.concept}
                        <div className="muted small-text">
                          {intent.description ?? intent.period} · vence{" "}
                          {formatDate(intent.due_date)}
                        </div>
                      </td>
                    </tr>
                    <tr>
                      <th>Monto del cobro</th>
                      <td>{formatCLP(intent.fee_amount)}</td>
                    </tr>
                    <tr>
                      <th>Ya pagado</th>
                      <td>{formatCLP(intent.fee_paid)}</td>
                    </tr>
                    <tr>
                      <th>Monto a pagar</th>
                      <td>
                        <strong>{formatCLP(intent.amount)}</strong>
                      </td>
                    </tr>
                    <tr>
                      <th>Medio de pago</th>
                      <td>Tarjeta de crédito (simulada)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div className="toolbar" style={{ marginTop: 16 }}>
                <button className="btn" onClick={confirm} disabled={busy}>
                  {busy ? "Procesando..." : "Pagar ahora"}
                </button>
                <button className="btn secondary" onClick={cancel} disabled={busy}>
                  Cancelar
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
