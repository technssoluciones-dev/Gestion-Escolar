"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, apiUpload } from "@/lib/api";
import { formatDate, todayISO } from "@/lib/dates";
import {
  CONCEPT_LABELS,
  FEE_STATUS_LABELS,
  PAYMENT_METHOD_LABELS,
  feeStatusTone,
  formatCLP,
} from "@/lib/money";

type Payment = {
  id: number;
  fee_id: number;
  amount: number;
  paid_on: string;
  method: string;
  reference: string | null;
  note: string | null;
};

type Fee = {
  id: number;
  student_id: number;
  student_name: string;
  student_rut: string;
  course_id: number | null;
  course_name: string | null;
  concept: string;
  description: string | null;
  period: string;
  amount: number;
  paid_amount: number;
  balance: number;
  due_date: string;
  status: string;
  payments: Payment[];
};

type Student = {
  id: number;
  full_name: string;
  rut: string;
  course: { id: number; name: string } | null;
};

type Course = { id: number; name: string; year: number };

type OnlineIntent = {
  id: number;
  token: string;
  status: "pendiente" | "pagada" | "cancelada";
  amount: number;
  provider: string;
  student_name: string;
  student_rut: string;
  course_name: string | null;
  concept: string;
  period: string;
  created_at: string;
  paid_at: string | null;
  payment_id: number | null;
};

type BankMovement = {
  id: number;
  movement_date: string;
  description: string;
  reference: string | null;
  amount: number;
  status: "pendiente" | "conciliado";
  fee_id: number | null;
  payment_id: number | null;
  student_name: string | null;
  fee_period: string | null;
  fee_concept: string | null;
};

const INTENT_STATUS_LABELS: Record<string, string> = {
  pendiente: "Pendiente",
  pagada: "Pagada",
  cancelada: "Cancelada",
};

function intentTone(status: string): string {
  if (status === "pagada") return "ok";
  if (status === "pendiente") return "warn";
  return "none";
}

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("es-CL", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

const MONTHS = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

function currentPeriod(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function formatPeriod(period: string): string {
  const [year, month] = period.split("-");
  const name = MONTHS[Number(month) - 1];
  return name ? `${name} ${year}` : period;
}

type FeeForm = {
  student_id: string;
  concept: string;
  period: string;
  amount: string;
  due_date: string;
  description: string;
};

function emptyFeeForm(): FeeForm {
  return {
    student_id: "",
    concept: "mensualidad",
    period: currentPeriod(),
    amount: "",
    due_date: todayISO(),
    description: "",
  };
}

type GenerateForm = {
  course_id: string;
  concept: string;
  period: string;
  amount: string;
  due_date: string;
  description: string;
};

function emptyGenerateForm(): GenerateForm {
  return {
    course_id: "",
    concept: "mensualidad",
    period: currentPeriod(),
    amount: "",
    due_date: todayISO(),
    description: "",
  };
}

type PaymentForm = {
  amount: string;
  method: string;
  paid_on: string;
  reference: string;
  note: string;
};

function emptyPaymentForm(amount: number | string = ""): PaymentForm {
  return {
    amount: String(amount),
    method: "transferencia",
    paid_on: todayISO(),
    reference: "",
    note: "",
  };
}

export default function PagosPage() {
  const [fees, setFees] = useState<Fee[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("todos");
  const [conceptFilter, setConceptFilter] = useState("todos");
  const [courseFilter, setCourseFilter] = useState("todos");
  const [periodFilter, setPeriodFilter] = useState("");

  const [feeModal, setFeeModal] = useState(false);
  const [feeForm, setFeeForm] = useState<FeeForm>(emptyFeeForm);
  const [generateModal, setGenerateModal] = useState(false);
  const [generateForm, setGenerateForm] = useState<GenerateForm>(emptyGenerateForm);
  const [payFee, setPayFee] = useState<Fee | null>(null);
  const [payForm, setPayForm] = useState<PaymentForm>(emptyPaymentForm);
  const [intents, setIntents] = useState<OnlineIntent[]>([]);
  const [intentStatus, setIntentStatus] = useState("todos");
  const [bank, setBank] = useState<BankMovement[]>([]);
  const [bankStatus, setBankStatus] = useState("todos");
  const [bankFile, setBankFile] = useState<File | null>(null);
  const [bankChoices, setBankChoices] = useState<Record<number, string>>({});
  const [bankBusy, setBankBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [feeResult, studentResult, courseResult, intentResult, bankResult] =
        await Promise.all([
          api<{ items: Fee[] }>("/fees?limit=200"),
          api<{ items: Student[] }>("/students?limit=200"),
          api<{ items: Course[] }>("/courses?limit=200"),
          api<{ items: OnlineIntent[] }>("/payments/intents?limit=100"),
          api<{ items: BankMovement[] }>("/payments/bank?limit=100"),
        ]);
      setFees(feeResult.items);
      setStudents(studentResult.items);
      setCourses(courseResult.items);
      setIntents(intentResult.items);
      setBank(bankResult.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron cargar los cobros");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return fees.filter((fee) => {
      if (statusFilter !== "todos" && fee.status !== statusFilter) return false;
      if (conceptFilter !== "todos" && fee.concept !== conceptFilter) return false;
      if (courseFilter !== "todos" && String(fee.course_id ?? "") !== courseFilter) return false;
      if (periodFilter && fee.period !== periodFilter) return false;
      if (!term) return true;
      return (
        fee.student_name.toLowerCase().includes(term) ||
        fee.student_rut.toLowerCase().includes(term) ||
        (fee.description ?? "").toLowerCase().includes(term)
      );
    });
  }, [fees, query, statusFilter, conceptFilter, courseFilter, periodFilter]);

  const summary = useMemo(() => {
    return filtered.reduce(
      (acc, fee) => {
        acc.charged += fee.amount;
        acc.collected += fee.paid_amount;
        acc.balance += fee.balance;
        if (fee.status === "vencida") acc.overdue += fee.balance;
        return acc;
      },
      { charged: 0, collected: 0, balance: 0, overdue: 0 },
    );
  }, [filtered]);

  const filteredIntents = useMemo(
    () =>
      intentStatus === "todos"
        ? intents
        : intents.filter((intent) => intent.status === intentStatus),
    [intents, intentStatus],
  );

  const filteredBank = useMemo(
    () =>
      bankStatus === "todos"
        ? bank
        : bank.filter((movement) => movement.status === bankStatus),
    [bank, bankStatus],
  );

  const openFees = useMemo(() => fees.filter((fee) => fee.balance > 0), [fees]);

  async function importBank() {
    if (!bankFile) {
      setError("Selecciona un archivo CSV.");
      return;
    }
    setBankBusy(true);
    setError("");
    setNotice("");
    const formData = new FormData();
    formData.append("file", bankFile);
    try {
      const result = await apiUpload<{
        imported: number;
        matched: number;
        pending: number;
        skipped: number;
      }>("/payments/bank/import", formData);
      setNotice(
        `Cartola importada: ${result.imported} movimientos, ${result.matched} conciliados` +
          (result.pending ? `, ${result.pending} por revisar` : "") +
          (result.skipped ? `, ${result.skipped} omitidos.` : "."),
      );
      setBankFile(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo importar la cartola");
    } finally {
      setBankBusy(false);
    }
  }

  async function matchBank(movement: BankMovement) {
    const choice = bankChoices[movement.id];
    if (!choice) {
      setError("Selecciona el cobro a conciliar.");
      return;
    }
    setBankBusy(true);
    setError("");
    setNotice("");
    try {
      await api(`/payments/bank/${movement.id}/match`, {
        method: "POST",
        body: { fee_id: Number(choice) },
      });
      setNotice("Movimiento conciliado y abono registrado.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo conciliar el movimiento");
    } finally {
      setBankBusy(false);
    }
  }

  function openNewFee() {
    setError("");
    setNotice("");
    setFeeForm(emptyFeeForm());
    setFeeModal(true);
  }

  async function saveFee(event: React.FormEvent) {
    event.preventDefault();
    if (!feeForm.student_id) {
      setError("Selecciona el estudiante.");
      return;
    }
    if (!feeForm.amount || Number(feeForm.amount) < 1) {
      setError("El monto debe ser mayor que cero.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await api("/fees", {
        method: "POST",
        body: {
          student_id: Number(feeForm.student_id),
          concept: feeForm.concept,
          period: feeForm.period,
          amount: Number(feeForm.amount),
          due_date: feeForm.due_date,
          description: feeForm.description.trim() || null,
        },
      });
      setNotice("Cobro registrado.");
      setFeeModal(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo registrar el cobro");
    } finally {
      setSaving(false);
    }
  }

  async function generateFees(event: React.FormEvent) {
    event.preventDefault();
    if (!generateForm.course_id) {
      setError("Selecciona el curso.");
      return;
    }
    if (!generateForm.amount || Number(generateForm.amount) < 1) {
      setError("El monto debe ser mayor que cero.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const result = await api<{ created: number; skipped: number }>("/fees/generate", {
        method: "POST",
        body: {
          course_id: Number(generateForm.course_id),
          concept: generateForm.concept,
          period: generateForm.period,
          amount: Number(generateForm.amount),
          due_date: generateForm.due_date,
          description: generateForm.description.trim() || null,
        },
      });
      setNotice(
        `Se crearon ${result.created} cobros` +
          (result.skipped ? ` y se omitieron ${result.skipped} que ya existían.` : "."),
      );
      setGenerateModal(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron generar los cobros");
    } finally {
      setSaving(false);
    }
  }

  async function removeFee(fee: Fee) {
    if (!window.confirm(`¿Eliminar el cobro de ${fee.student_name}?`)) return;
    setError("");
    setNotice("");
    try {
      await api(`/fees/${fee.id}`, { method: "DELETE" });
      setNotice("Cobro eliminado.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo eliminar el cobro");
    }
  }

  function openPayment(fee: Fee) {
    setError("");
    setNotice("");
    setPayFee(fee);
    setPayForm(emptyPaymentForm(fee.balance));
  }

  async function refreshFee(feeId: number) {
    const fresh = await api<Fee>(`/fees/${feeId}`);
    setPayFee(fresh);
    setPayForm(emptyPaymentForm(fresh.balance));
    return fresh;
  }

  async function registerPayment(event: React.FormEvent) {
    event.preventDefault();
    if (!payFee) return;
    const amount = Number(payForm.amount);
    if (!amount || amount < 1) {
      setError("El monto del pago debe ser mayor que cero.");
      return;
    }
    if (amount > payFee.balance) {
      setError(`El monto supera el saldo pendiente (${formatCLP(payFee.balance)}).`);
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await api(`/fees/${payFee.id}/payments`, {
        method: "POST",
        body: {
          amount,
          method: payForm.method,
          paid_on: payForm.paid_on,
          reference: payForm.reference.trim() || null,
          note: payForm.note.trim() || null,
        },
      });
      setNotice("Pago registrado.");
      await refreshFee(payFee.id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo registrar el pago");
    } finally {
      setSaving(false);
    }
  }

  async function removePayment(payment: Payment) {
    if (!payFee) return;
    if (!window.confirm(`¿Eliminar el pago de ${formatCLP(payment.amount)}?`)) return;
    setError("");
    setNotice("");
    try {
      await api(`/fees/${payFee.id}/payments/${payment.id}`, { method: "DELETE" });
      setNotice("Pago eliminado.");
      await refreshFee(payFee.id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo eliminar el pago");
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Pagos</h1>
          <p>Matrículas, mensualidades y cuotas, con sus abonos.</p>
        </div>
        <div className="toolbar" style={{ margin: 0 }}>
          <button
            className="btn secondary"
            onClick={() => {
              setError("");
              setNotice("");
              setGenerateForm(emptyGenerateForm());
              setGenerateModal(true);
            }}
          >
            Generar por curso
          </button>
          <button className="btn" onClick={openNewFee}>
            Nuevo cobro
          </button>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}
      {notice && <div className="notice">{notice}</div>}

      <div className="mini-stats">
        <div className="mini-stat">
          <div className="n">{formatCLP(summary.charged)}</div>
          <div className="l">Total cobrado</div>
        </div>
        <div className="mini-stat">
          <div className="n ok">{formatCLP(summary.collected)}</div>
          <div className="l">Recaudado</div>
        </div>
        <div className="mini-stat">
          <div className="n warn">{formatCLP(summary.balance)}</div>
          <div className="l">Saldo pendiente</div>
        </div>
        <div className="mini-stat">
          <div className="n bad">{formatCLP(summary.overdue)}</div>
          <div className="l">Saldo vencido</div>
        </div>
      </div>

      <div className="filters">
        <div>
          <label htmlFor="q">Buscar</label>
          <input
            id="q"
            type="search"
            placeholder="Estudiante, RUT o descripción..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="status">Estado</label>
          <select id="status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="todos">Todos los estados</option>
            {Object.entries(FEE_STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="concept">Tipo</label>
          <select id="concept" value={conceptFilter} onChange={(e) => setConceptFilter(e.target.value)}>
            <option value="todos">Todos los tipos</option>
            {Object.entries(CONCEPT_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="course-filter">Curso</label>
          <select
            id="course-filter"
            value={courseFilter}
            onChange={(e) => setCourseFilter(e.target.value)}
          >
            <option value="todos">Todos los cursos</option>
            {courses.map((course) => (
              <option key={course.id} value={course.id}>
                {course.name} ({course.year})
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="period-filter">Período</label>
          <input
            id="period-filter"
            type="month"
            value={periodFilter}
            onChange={(e) => setPeriodFilter(e.target.value)}
          />
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Estudiante</th>
              <th>Curso</th>
              <th>Cobro</th>
              <th>Monto</th>
              <th>Pagado</th>
              <th>Saldo</th>
              <th>Vence</th>
              <th>Estado</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filtered.map((fee) => (
              <tr key={fee.id}>
                <td>
                  <strong>{fee.student_name}</strong>
                  <div className="muted small-text">{fee.student_rut}</div>
                </td>
                <td>{fee.course_name ?? <span className="muted">Sin curso</span>}</td>
                <td>
                  {CONCEPT_LABELS[fee.concept] ?? fee.concept}
                  <div className="muted small-text">
                    {formatPeriod(fee.period)}
                    {fee.description ? ` · ${fee.description}` : ""}
                  </div>
                </td>
                <td>{formatCLP(fee.amount)}</td>
                <td>
                  {formatCLP(fee.paid_amount)}
                  {fee.payments.length > 0 && (
                    <div className="muted small-text">
                      {fee.payments.length} pago{fee.payments.length === 1 ? "" : "s"}
                    </div>
                  )}
                </td>
                <td>
                  <strong>{formatCLP(fee.balance)}</strong>
                </td>
                <td>{formatDate(fee.due_date)}</td>
                <td>
                  <span className={`badge ${feeStatusTone(fee.status)}`}>
                    {FEE_STATUS_LABELS[fee.status] ?? fee.status}
                  </span>
                </td>
                <td>
                  <div className="row-actions">
                    <button className="btn small" onClick={() => openPayment(fee)}>
                      {fee.balance > 0 ? "Abonar" : "Ver pagos"}
                    </button>
                    {fee.payments.length === 0 && (
                      <button className="btn small danger" onClick={() => removeFee(fee)}>
                        Eliminar
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="empty">Cargando cobros...</div>}
        {!loading && filtered.length === 0 && (
          <div className="empty">
            {fees.length === 0 ? (
              <>
                Aún no hay cobros.{" "}
                <button className="btn small" onClick={openNewFee}>
                  Registrar el primero
                </button>
              </>
            ) : (
              "No hay cobros que coincidan con los filtros."
            )}
          </div>
        )}
      </div>

      <p className="muted small-text" style={{ marginTop: 10 }}>
        Un cobro puede pagarse en varias veces. Con pagos registrados no se puede editar ni
        eliminar; si te equivocaste, elimina el pago correspondiente.
      </p>

      <div className="card" style={{ marginTop: 18 }}>
        <div className="page-head" style={{ marginBottom: 10 }}>
          <div>
            <h2>Pagos en línea</h2>
            <p className="muted small-text">
              Transacciones iniciadas desde el portal de familias, para conciliar con los abonos
              de cada cobro.
            </p>
          </div>
          <div className="toolbar" style={{ margin: 0 }}>
            <select
              aria-label="Estado del pago en línea"
              value={intentStatus}
              onChange={(e) => setIntentStatus(e.target.value)}
            >
              <option value="todos">Todos los estados</option>
              {Object.entries(INTENT_STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <button className="btn secondary small" onClick={load}>
              Actualizar
            </button>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Iniciado</th>
                <th>Estudiante</th>
                <th>Cobro</th>
                <th>Monto</th>
                <th>Estado</th>
                <th>Abono</th>
              </tr>
            </thead>
            <tbody>
              {filteredIntents.map((intent) => (
                <tr key={intent.id}>
                  <td>{formatDateTime(intent.created_at)}</td>
                  <td>
                    <strong>{intent.student_name}</strong>
                    <div className="muted small-text">{intent.student_rut}</div>
                  </td>
                  <td>
                    {CONCEPT_LABELS[intent.concept] ?? intent.concept}
                    <div className="muted small-text">{formatPeriod(intent.period)}</div>
                  </td>
                  <td>{formatCLP(intent.amount)}</td>
                  <td>
                    <span className={`badge ${intentTone(intent.status)}`}>
                      {INTENT_STATUS_LABELS[intent.status] ?? intent.status}
                    </span>
                    {intent.paid_at && (
                      <div className="muted small-text">{formatDateTime(intent.paid_at)}</div>
                    )}
                  </td>
                  <td>
                    {intent.payment_id ? (
                      <>
                        Pago #{intent.payment_id}
                        <div className="muted small-text">
                          {intent.provider === "webpay"
                            ? "WEBPAY"
                            : `ONLINE-${intent.token.slice(0, 10).toUpperCase()}`}
                        </div>
                      </>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filteredIntents.length === 0 && (
            <div className="empty">
              {intents.length === 0
                ? "Aún no hay pagos en línea. Las familias los inician desde el portal."
                : "No hay pagos en línea con ese estado."}
            </div>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <div className="page-head" style={{ marginBottom: 10 }}>
          <div>
            <h2>Conciliación bancaria</h2>
            <p className="muted small-text">
              Importa la cartola en CSV (fecha, descripcion, monto) y el sistema busca el cobro por
              RUT o referencia. Los movimientos sin coincidencia se concilian a mano.
            </p>
          </div>
          <div className="toolbar" style={{ margin: 0 }}>
            <input
              type="file"
              accept=".csv,text/csv"
              aria-label="Archivo de cartola"
              onChange={(e) => setBankFile(e.target.files?.[0] ?? null)}
            />
            <button
              className="btn small"
              disabled={!bankFile || bankBusy}
              onClick={importBank}
            >
              {bankBusy ? "Procesando..." : "Importar cartola"}
            </button>
            <select
              aria-label="Estado de conciliación"
              value={bankStatus}
              onChange={(e) => setBankStatus(e.target.value)}
            >
              <option value="todos">Todos los estados</option>
              <option value="pendiente">Pendientes</option>
              <option value="conciliado">Conciliados</option>
            </select>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Descripción</th>
                <th>Monto</th>
                <th>Estado</th>
                <th>Cobro</th>
                <th>Acción</th>
              </tr>
            </thead>
            <tbody>
              {filteredBank.map((movement) => (
                <tr key={movement.id}>
                  <td>{formatDate(movement.movement_date)}</td>
                  <td>
                    {movement.description}
                    {movement.reference && (
                      <div className="muted small-text">Ref. {movement.reference}</div>
                    )}
                  </td>
                  <td>{formatCLP(movement.amount)}</td>
                  <td>
                    <span
                      className={`badge ${movement.status === "conciliado" ? "ok" : "warn"}`}
                    >
                      {movement.status === "conciliado" ? "Conciliado" : "Pendiente"}
                    </span>
                  </td>
                  <td>
                    {movement.student_name ? (
                      <>
                        {movement.student_name}
                        <div className="muted small-text">
                          {movement.fee_concept
                            ? (CONCEPT_LABELS[movement.fee_concept] ?? movement.fee_concept)
                            : ""}
                          {movement.fee_period ? ` · ${formatPeriod(movement.fee_period)}` : ""}
                          {movement.payment_id ? ` · Pago #${movement.payment_id}` : ""}
                        </div>
                      </>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td>
                    {movement.status === "pendiente" ? (
                      <div className="row-actions">
                        <select
                          aria-label={`Cobro para el movimiento ${movement.id}`}
                          value={bankChoices[movement.id] ?? ""}
                          onChange={(e) =>
                            setBankChoices((prev) => ({
                              ...prev,
                              [movement.id]: e.target.value,
                            }))
                          }
                        >
                          <option value="">Elegir cobro...</option>
                          {openFees.map((fee) => (
                            <option key={fee.id} value={fee.id}>
                              {fee.student_name} · {formatPeriod(fee.period)} ·{" "}
                              {formatCLP(fee.balance)}
                            </option>
                          ))}
                        </select>
                        <button
                          className="btn small"
                          disabled={bankBusy || !bankChoices[movement.id]}
                          onClick={() => matchBank(movement)}
                        >
                          Conciliar
                        </button>
                      </div>
                    ) : (
                      <span className="muted small-text">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filteredBank.length === 0 && (
            <div className="empty">
              {bank.length === 0
                ? "Aún no hay movimientos. Importa la cartola del banco en CSV."
                : "No hay movimientos con ese estado."}
            </div>
          )}
        </div>
      </div>

      {feeModal && (
        <div className="overlay">
          <div className="modal">
            <div className="modal-head">
              <h2>Nuevo cobro</h2>
              <button className="btn secondary small" onClick={() => setFeeModal(false)}>
                Cerrar
              </button>
            </div>
            <form onSubmit={saveFee}>
              <div className="form-grid">
                <div className="full">
                  <label htmlFor="fee-student">
                    Estudiante <span className="req">*</span>
                  </label>
                  <select
                    id="fee-student"
                    value={feeForm.student_id}
                    onChange={(e) => setFeeForm({ ...feeForm, student_id: e.target.value })}
                    required
                  >
                    <option value="">Selecciona un estudiante</option>
                    {students.map((student) => (
                      <option key={student.id} value={student.id}>
                        {student.full_name}
                        {student.course ? ` · ${student.course.name}` : ""}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="fee-concept">Tipo</label>
                  <select
                    id="fee-concept"
                    value={feeForm.concept}
                    onChange={(e) => setFeeForm({ ...feeForm, concept: e.target.value })}
                  >
                    {Object.entries(CONCEPT_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="fee-period">
                    Período <span className="req">*</span>
                  </label>
                  <input
                    id="fee-period"
                    type="month"
                    value={feeForm.period}
                    onChange={(e) => setFeeForm({ ...feeForm, period: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="fee-amount">
                    Monto (CLP) <span className="req">*</span>
                  </label>
                  <input
                    id="fee-amount"
                    type="number"
                    min="1"
                    step="1"
                    value={feeForm.amount}
                    onChange={(e) => setFeeForm({ ...feeForm, amount: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="fee-due">
                    Vencimiento <span className="req">*</span>
                  </label>
                  <input
                    id="fee-due"
                    type="date"
                    value={feeForm.due_date}
                    onChange={(e) => setFeeForm({ ...feeForm, due_date: e.target.value })}
                    required
                  />
                </div>
                <div className="full">
                  <label htmlFor="fee-description">Descripción</label>
                  <input
                    id="fee-description"
                    type="text"
                    placeholder="Ej: Mensualidad marzo"
                    value={feeForm.description}
                    onChange={(e) => setFeeForm({ ...feeForm, description: e.target.value })}
                  />
                </div>
              </div>
              <div className="modal-foot">
                <button type="button" className="btn secondary" onClick={() => setFeeModal(false)}>
                  Cancelar
                </button>
                <button className="btn" disabled={saving}>
                  {saving ? "Guardando..." : "Guardar cobro"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {generateModal && (
        <div className="overlay">
          <div className="modal">
            <div className="modal-head">
              <h2>Generar cobros por curso</h2>
              <button className="btn secondary small" onClick={() => setGenerateModal(false)}>
                Cerrar
              </button>
            </div>
            <form onSubmit={generateFees}>
              <p className="muted small-text" style={{ marginTop: 0 }}>
                Crea un cobro para cada estudiante activo del curso. Se omiten los estudiantes que
                ya tienen un cobro del mismo tipo y período.
              </p>
              <div className="form-grid">
                <div className="full">
                  <label htmlFor="gen-course">
                    Curso <span className="req">*</span>
                  </label>
                  <select
                    id="gen-course"
                    value={generateForm.course_id}
                    onChange={(e) => setGenerateForm({ ...generateForm, course_id: e.target.value })}
                    required
                  >
                    <option value="">Selecciona un curso</option>
                    {courses.map((course) => (
                      <option key={course.id} value={course.id}>
                        {course.name} ({course.year})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="gen-concept">Tipo</label>
                  <select
                    id="gen-concept"
                    value={generateForm.concept}
                    onChange={(e) => setGenerateForm({ ...generateForm, concept: e.target.value })}
                  >
                    {Object.entries(CONCEPT_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="gen-period">
                    Período <span className="req">*</span>
                  </label>
                  <input
                    id="gen-period"
                    type="month"
                    value={generateForm.period}
                    onChange={(e) => setGenerateForm({ ...generateForm, period: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="gen-amount">
                    Monto por estudiante (CLP) <span className="req">*</span>
                  </label>
                  <input
                    id="gen-amount"
                    type="number"
                    min="1"
                    step="1"
                    value={generateForm.amount}
                    onChange={(e) => setGenerateForm({ ...generateForm, amount: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="gen-due">
                    Vencimiento <span className="req">*</span>
                  </label>
                  <input
                    id="gen-due"
                    type="date"
                    value={generateForm.due_date}
                    onChange={(e) => setGenerateForm({ ...generateForm, due_date: e.target.value })}
                    required
                  />
                </div>
                <div className="full">
                  <label htmlFor="gen-description">Descripción</label>
                  <input
                    id="gen-description"
                    type="text"
                    value={generateForm.description}
                    onChange={(e) => setGenerateForm({ ...generateForm, description: e.target.value })}
                  />
                </div>
              </div>
              <div className="modal-foot">
                <button type="button" className="btn secondary" onClick={() => setGenerateModal(false)}>
                  Cancelar
                </button>
                <button className="btn" disabled={saving}>
                  {saving ? "Generando..." : "Generar cobros"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {payFee && (
        <div className="overlay">
          <div className="modal wide">
            <div className="modal-head">
              <h2>Pagos del cobro</h2>
              <button className="btn secondary small" onClick={() => setPayFee(null)}>
                Cerrar
              </button>
            </div>

            <p>
              <strong>{payFee.student_name}</strong> · {CONCEPT_LABELS[payFee.concept] ?? payFee.concept} ·{" "}
              {formatPeriod(payFee.period)}
            </p>
            <div className="form-grid">
              <div>
                <span className="muted small-text">Monto</span>
                <div>
                  <strong>{formatCLP(payFee.amount)}</strong>
                </div>
              </div>
              <div>
                <span className="muted small-text">Pagado</span>
                <div>
                  <strong>{formatCLP(payFee.paid_amount)}</strong>
                </div>
              </div>
              <div>
                <span className="muted small-text">Saldo</span>
                <div>
                  <strong>{formatCLP(payFee.balance)}</strong>
                </div>
              </div>
              <div>
                <span className="muted small-text">Vence</span>
                <div>{formatDate(payFee.due_date)}</div>
              </div>
              <div>
                <span className="muted small-text">Estado</span>
                <div>
                  <span className={`badge ${feeStatusTone(payFee.status)}`}>
                    {FEE_STATUS_LABELS[payFee.status] ?? payFee.status}
                  </span>
                </div>
              </div>
            </div>

            <h3 className="form-section">Pagos registrados</h3>
            {payFee.payments.length === 0 ? (
              <p className="muted">Aún no hay pagos para este cobro.</p>
            ) : (
              <div className="table-wrap" style={{ marginBottom: 16 }}>
                <table>
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th>Monto</th>
                      <th>Medio</th>
                      <th>Referencia</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {payFee.payments.map((payment) => (
                      <tr key={payment.id}>
                        <td>{formatDate(payment.paid_on)}</td>
                        <td>{formatCLP(payment.amount)}</td>
                        <td>{PAYMENT_METHOD_LABELS[payment.method] ?? payment.method}</td>
                        <td>{payment.reference ?? <span className="muted">—</span>}</td>
                        <td>
                          <div className="row-actions">
                            <button
                              className="btn small danger"
                              onClick={() => removePayment(payment)}
                            >
                              Eliminar
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {payFee.balance > 0 ? (
              <form onSubmit={registerPayment}>
                <h3 className="form-section">Registrar pago</h3>
                <div className="form-grid">
                  <div>
                    <label htmlFor="pay-amount">
                      Monto (CLP) <span className="req">*</span>
                    </label>
                    <input
                      id="pay-amount"
                      type="number"
                      min="1"
                      max={payFee.balance}
                      step="1"
                      value={payForm.amount}
                      onChange={(e) => setPayForm({ ...payForm, amount: e.target.value })}
                      required
                    />
                  </div>
                  <div>
                    <label htmlFor="pay-method">Medio de pago</label>
                    <select
                      id="pay-method"
                      value={payForm.method}
                      onChange={(e) => setPayForm({ ...payForm, method: e.target.value })}
                    >
                      {Object.entries(PAYMENT_METHOD_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="pay-date">
                      Fecha <span className="req">*</span>
                    </label>
                    <input
                      id="pay-date"
                      type="date"
                      max={todayISO()}
                      value={payForm.paid_on}
                      onChange={(e) => setPayForm({ ...payForm, paid_on: e.target.value })}
                      required
                    />
                  </div>
                  <div>
                    <label htmlFor="pay-reference">Referencia</label>
                    <input
                      id="pay-reference"
                      type="text"
                      placeholder="N° transferencia, boleta..."
                      value={payForm.reference}
                      onChange={(e) => setPayForm({ ...payForm, reference: e.target.value })}
                    />
                  </div>
                  <div className="full">
                    <label htmlFor="pay-note">Nota</label>
                    <input
                      id="pay-note"
                      type="text"
                      value={payForm.note}
                      onChange={(e) => setPayForm({ ...payForm, note: e.target.value })}
                    />
                  </div>
                </div>
                <div className="modal-foot">
                  <button type="button" className="btn secondary" onClick={() => setPayFee(null)}>
                    Cerrar
                  </button>
                  <button className="btn" disabled={saving}>
                    {saving ? "Registrando..." : "Registrar pago"}
                  </button>
                </div>
              </form>
            ) : (
              <div className="modal-foot">
                <button className="btn secondary" onClick={() => setPayFee(null)}>
                  Cerrar
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
