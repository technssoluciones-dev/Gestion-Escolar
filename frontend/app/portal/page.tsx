"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/dates";
import {
  CONCEPT_LABELS,
  FEE_STATUS_LABELS,
  feeStatusTone,
  formatCLP,
} from "@/lib/money";

type Child = {
  id: number;
  full_name: string;
  rut: string;
  birth_date: string;
  status: string;
  course: { id: number; name: string; year: number } | null;
};

type Me = {
  id: number;
  email: string;
  full_name: string;
  role: "apoderado" | "estudiante";
  guardian: { id: number; full_name: string; phone: string | null } | null;
  student: Child | null;
};

type Grade = {
  id: number;
  title: string;
  score: number;
  weight: number;
  date: string;
};

type Fee = {
  id: number;
  concept: string;
  description: string | null;
  period: string;
  amount: number;
  paid_amount: number;
  balance: number;
  due_date: string;
  status: string;
};

type Notice = {
  id: number;
  type: string;
  title: string;
  message: string;
  period: string;
  sent_at: string | null;
  created_at: string;
};

const NOTICE_TYPE_LABELS: Record<string, string> = {
  inasistencia: "Asistencia",
  notas: "Notas",
  deuda: "Pagos",
  general: "General",
};

type Overview = {
  student: Child;
  attendance: {
    from_date: string;
    to_date: string;
    total: number;
    presente: number;
    ausente: number;
    atrasado: number;
    justificado: number;
    rate: number | null;
  };
  subjects: {
    subject: { id: number; name: string; code: string | null };
    grades: Grade[];
    average: number | null;
    count: number;
  }[];
  overall: number | null;
  fees: Fee[];
  pending_amount: number;
  overdue_amount: number;
};

function gradeTone(score: number): string {
  return score >= 4 ? "ok" : "bad";
}

function periodLabel(period: string): string {
  const [year, month] = period.split("-");
  const months = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
  ];
  return months[Number(month) - 1] ? `${months[Number(month) - 1]} ${year}` : period;
}

export default function PortalPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [children, setChildren] = useState<Child[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payingId, setPayingId] = useState<number | null>(null);
  const [webpay, setWebpay] = useState<{ url: string; token: string } | null>(null);
  const webpayForm = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (webpay) webpayForm.current?.submit();
  }, [webpay]);

  const loadProfile = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [profile, kids] = await Promise.all([
        api<Me>("/portal/me"),
        api<Child[]>("/portal/children"),
      ]);
      setMe(profile);
      setChildren(kids);
      setSelected(kids.length ? kids[0].id : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar tu información");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  useEffect(() => {
    if (!selected) {
      setOverview(null);
      setNotices([]);
      return;
    }
    setOverview(null);
    setNotices([]);
    Promise.all([
      api<Overview>(`/portal/students/${selected}`),
      api<Notice[]>(`/portal/notifications?student_id=${selected}`),
    ])
      .then(([profile, avisos]) => {
        setOverview(profile);
        setNotices(avisos);
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "No se pudo cargar la ficha"),
      );
  }, [selected]);

  if (loading) return <p className="muted">Cargando portal...</p>;
  if (error && !me) return <div className="alert">{error}</div>;

  const isGuardian = me?.role === "apoderado";

  async function payOnline(feeId: number) {
    setPayingId(feeId);
    setError("");
    try {
      const data = await api<{
        checkout_url: string;
        provider: string;
        webpay_url: string | null;
        webpay_token: string | null;
      }>("/payments/checkout", {
        method: "POST",
        body: { fee_id: feeId },
      });
      if (data.provider === "webpay" && data.webpay_url && data.webpay_token) {
        setWebpay({ url: data.webpay_url, token: data.webpay_token });
        return;
      }
      router.push(data.checkout_url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo iniciar el pago");
      setPayingId(null);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{isGuardian ? "Portal de familias" : "Mi información"}</h1>
          <p>
            {isGuardian
              ? `Hola ${me?.full_name ?? ""}. Revisa la asistencia, las notas y los pagos de tus estudiantes.`
              : `Hola ${me?.full_name ?? ""}. Revisa tu asistencia, tus notas y tus pagos.`}
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      {children.length === 0 ? (
        <div className="table-wrap">
          <div className="empty">
            No hay estudiantes asociados a tu cuenta. Comunícate con la secretaría del colegio.
          </div>
        </div>
      ) : (
        <>
          <div className="child-list">
            {children.map((child) => (
              <button
                key={child.id}
                className={`child-chip ${selected === child.id ? "active" : ""}`}
                onClick={() => setSelected(child.id)}
              >
                <strong>{child.full_name}</strong>
                <span>{child.course ? child.course.name : "Sin curso"}</span>
              </button>
            ))}
          </div>

          {!overview ? (
            <p className="muted">Cargando la ficha del estudiante...</p>
          ) : (
            <>
              <div className="mini-stats">
                <div className="mini-stat">
                  <div className="n">{overview.attendance.rate == null ? "—" : `${overview.attendance.rate}%`}</div>
                  <div className="l">Asistencia (60 días)</div>
                </div>
                <div className="mini-stat">
                  <div className="n">{overview.overall == null ? "—" : overview.overall.toFixed(1)}</div>
                  <div className="l">Promedio general</div>
                </div>
                <div className="mini-stat">
                  <div className="n warn">{formatCLP(overview.pending_amount)}</div>
                  <div className="l">Saldo pendiente</div>
                </div>
                <div className="mini-stat">
                  <div className="n bad">{formatCLP(overview.overdue_amount)}</div>
                  <div className="l">Saldo vencido</div>
                </div>
              </div>

              {notices.length > 0 && (
                <div className="card" style={{ marginBottom: 18 }}>
                  <h2>Avisos del colegio</h2>
                  <div className="notice-list">
                    {notices.map((notice) => (
                      <div key={notice.id} className="notice-item">
                        <div className="notice-item-head">
                          <span className="badge info">
                            {NOTICE_TYPE_LABELS[notice.type] ?? notice.type}
                          </span>
                          <strong>{notice.title}</strong>
                        </div>
                        <p>{notice.message}</p>
                        <div className="meta">
                          {notice.sent_at ? `Publicado el ${formatDate(notice.sent_at)} · ` : ""}
                          Período {periodLabel(notice.period)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="grid-2">
                <div className="card">
                  <h2>Asistencia</h2>
                  <p className="muted small-text" style={{ marginTop: -6 }}>
                    Desde {formatDate(overview.attendance.from_date)} hasta{" "}
                    {formatDate(overview.attendance.to_date)}
                  </p>
                  {overview.attendance.total === 0 ? (
                    <p className="muted">Aún no hay registros de asistencia en este período.</p>
                  ) : (
                    <div className="chips">
                      <span className="chip ok">Presente: {overview.attendance.presente}</span>
                      <span className="chip warn">Atrasado: {overview.attendance.atrasado}</span>
                      <span className="chip bad">Ausente: {overview.attendance.ausente}</span>
                      <span className="chip">Justificado: {overview.attendance.justificado}</span>
                    </div>
                  )}
                </div>

                <div className="card">
                  <h2>Estudiante</h2>
                  <p style={{ margin: "4px 0" }}>
                    <strong>{overview.student.full_name}</strong>
                  </p>
                  <p className="muted small-text" style={{ margin: "4px 0" }}>
                    {overview.student.rut} · Nacimiento: {formatDate(overview.student.birth_date)}
                  </p>
                  <p className="muted small-text" style={{ margin: "4px 0" }}>
                    Curso: {overview.student.course ? overview.student.course.name : "Sin curso"}
                  </p>
                  <p className="muted small-text" style={{ margin: "4px 0" }}>
                    Estado: {overview.student.status}
                  </p>
                </div>
              </div>

              <div className="card" style={{ marginTop: 18 }}>
                <h2>Notas por asignatura</h2>
                {overview.subjects.length === 0 ? (
                  <p className="muted">Aún no hay notas registradas.</p>
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Asignatura</th>
                          <th>Evaluaciones</th>
                          <th>Promedio</th>
                        </tr>
                      </thead>
                      <tbody>
                        {overview.subjects.map((row) => (
                          <tr key={row.subject.id}>
                            <td>
                              <strong>{row.subject.name}</strong>
                              {row.subject.code && (
                                <div className="muted small-text">{row.subject.code}</div>
                              )}
                            </td>
                            <td>
                              <div className="chips">
                                {row.grades.map((grade) => (
                                  <span
                                    key={grade.id}
                                    className={`chip ${gradeTone(grade.score)}`}
                                    title={`${grade.title} · ${formatDate(grade.date)} · ponderación ${grade.weight}`}
                                  >
                                    {grade.title}: {grade.score.toFixed(1)}
                                  </span>
                                ))}
                              </div>
                            </td>
                            <td>
                              {row.average == null ? (
                                <span className="muted">—</span>
                              ) : (
                                <span className={`badge ${gradeTone(row.average)}`}>
                                  {row.average.toFixed(1)}
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="card" style={{ marginTop: 18 }}>
                <h2>Cobros y pagos</h2>
                {overview.fees.length === 0 ? (
                  <p className="muted">No hay cobros registrados para este estudiante.</p>
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Cobro</th>
                          <th>Vence</th>
                          <th>Monto</th>
                          <th>Pagado</th>
                          <th>Saldo</th>
                          <th>Estado</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {overview.fees.map((fee) => (
                          <tr key={fee.id}>
                            <td>
                              <strong>{CONCEPT_LABELS[fee.concept] ?? fee.concept}</strong>
                              <div className="muted small-text">
                                {fee.description ?? periodLabel(fee.period)}
                              </div>
                            </td>
                            <td>{formatDate(fee.due_date)}</td>
                            <td>{formatCLP(fee.amount)}</td>
                            <td>{formatCLP(fee.paid_amount)}</td>
                            <td>
                              <strong>{formatCLP(fee.balance)}</strong>
                            </td>
                            <td>
                              <span className={`badge ${feeStatusTone(fee.status)}`}>
                                {FEE_STATUS_LABELS[fee.status] ?? fee.status}
                              </span>
                            </td>
                            <td>
                              {fee.balance > 0 && (
                                <button
                                  className="btn small"
                                  disabled={payingId !== null}
                                  onClick={() => payOnline(fee.id)}
                                >
                                  {payingId === fee.id ? "Abriendo..." : "Pagar en línea"}
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <p className="muted small-text" style={{ marginTop: 10 }}>
                  El pago en línea abre una pasarela de prueba: al confirmar, el abono queda
                  registrado en el cobro.
                </p>
              </div>
            </>
          )}
        </>
      )}
      {webpay && (
        <div className="card">
          <p className="muted">Redirigiendo a Webpay...</p>
          <form ref={webpayForm} action={webpay.url} method="POST">
            <input type="hidden" name="token_ws" value={webpay.token} />
            <button className="btn" type="submit">
              Continuar a Webpay
            </button>
          </form>
        </div>
      )}
    </>
  );
}
