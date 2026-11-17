"use client";

/**
 * Pantalla reutilizable: buscador + tabla + paginación + ventana para crear/editar.
 * Cada sección (estudiantes, profesores...) solo define sus columnas y campos.
 */
import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatRut, isValidRut } from "@/lib/rut";

export type Option = { value: string | number; label: string };

export type Field = {
  name: string;
  label: string;
  type: "text" | "email" | "date" | "number" | "rut" | "select" | "checkbox";
  required?: boolean;
  full?: boolean; // ocupa las dos columnas
  options?: Option[]; // opciones fijas
  optionsFrom?: { path: string; label: (item: any) => string }; // opciones desde el backend
  defaultValue?: string | number | boolean;
};

export type Column = { header: string; render: (row: any) => ReactNode };

type Props = {
  title: string;
  subtitle: string;
  singular: string; // "estudiante"
  endpoint: string; // "/students"
  columns: Column[];
  fields: Field[];
  searchPlaceholder?: string;
  searchable?: boolean;
  filter?: { param: string; label: string; optionsFrom: { path: string; label: (item: any) => string } };
  deleteMessage?: string;
  pageSize?: number;
};

type Modal = { mode: "new" } | { mode: "edit"; row: any } | null;

export default function CrudPage(props: Props) {
  const { title, subtitle, singular, endpoint, columns, fields, searchable = true, filter } = props;
  const pageSize = props.pageSize ?? 15;

  const [rows, setRows] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [filterValue, setFilterValue] = useState("");
  const [filterOptions, setFilterOptions] = useState<Option[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modal, setModal] = useState<Modal>(null);
  const [fieldOptions, setFieldOptions] = useState<Record<string, Option[]>>({});

  // Espera un momento antes de buscar mientras se escribe
  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search);
      setPage(0);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ skip: String(page * pageSize), limit: String(pageSize) });
    if (debounced) params.set("q", debounced);
    if (filter && filterValue) params.set(filter.param, filterValue);
    try {
      const data = await api<{ items: any[]; total: number }>(`${endpoint}?${params}`);
      setRows(data.items);
      setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    } finally {
      setLoading(false);
    }
  }, [endpoint, page, pageSize, debounced, filter, filterValue]);

  useEffect(() => {
    load();
  }, [load]);

  // Carga las listas para los campos tipo "select" (cursos, apoderados...)
  useEffect(() => {
    const sources = fields.filter((f) => f.optionsFrom);
    sources.forEach((f) => {
      api<{ items: any[] }>(`${f.optionsFrom!.path}?limit=200`)
        .then((d) =>
          setFieldOptions((prev) => ({
            ...prev,
            [f.name]: d.items.map((i) => ({ value: i.id, label: f.optionsFrom!.label(i) })),
          })),
        )
        .catch(() => {});
    });
    if (filter) {
      api<{ items: any[] }>(`${filter.optionsFrom.path}?limit=200`)
        .then((d) => setFilterOptions(d.items.map((i) => ({ value: i.id, label: filter.optionsFrom.label(i) }))))
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function remove(row: any) {
    const name = row.full_name ?? row.name;
    if (!window.confirm(props.deleteMessage ?? `¿Eliminar ${singular} "${name}"?`)) return;
    try {
      await api(`${endpoint}/${row.id}`, { method: "DELETE" });
      if (rows.length === 1 && page > 0) setPage(page - 1);
      else load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo eliminar");
    }
  }

  const pages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        <button className="btn" onClick={() => setModal({ mode: "new" })}>
          + Nuevo {singular}
        </button>
      </div>

      <div className="toolbar">
        {searchable && (
          <input
            placeholder={props.searchPlaceholder ?? "Buscar por nombre o RUT..."}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        )}
        {filter && (
          <select
            value={filterValue}
            onChange={(e) => {
              setFilterValue(e.target.value);
              setPage(0);
            }}
          >
            <option value="">{filter.label}</option>
            {filterOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        )}
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.header}>{c.header}</th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                {columns.map((c) => (
                  <td key={c.header}>{c.render(row)}</td>
                ))}
                <td>
                  <div className="row-actions">
                    <button className="btn secondary small" onClick={() => setModal({ mode: "edit", row })}>
                      Editar
                    </button>
                    <button className="btn danger small" onClick={() => remove(row)}>
                      Eliminar
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && rows.length === 0 && <div className="empty">No hay resultados.</div>}
        {loading && rows.length === 0 && <div className="empty">Cargando...</div>}
      </div>

      <div className="pager">
        <span>
          {total} {total === 1 ? "registro" : "registros"}
        </span>
        <div>
          <button className="btn secondary small" disabled={page === 0} onClick={() => setPage(page - 1)}>
            ← Anterior
          </button>
          <span style={{ alignSelf: "center" }}>
            Página {page + 1} de {pages}
          </span>
          <button className="btn secondary small" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>
            Siguiente →
          </button>
        </div>
      </div>

      {modal && (
        <FormModal
          singular={singular}
          endpoint={endpoint}
          fields={fields}
          fieldOptions={fieldOptions}
          row={modal.mode === "edit" ? modal.row : null}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null);
            load();
          }}
        />
      )}
    </>
  );
}

function FormModal(props: {
  singular: string;
  endpoint: string;
  fields: Field[];
  fieldOptions: Record<string, Option[]>;
  row: any | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { fields, row } = props;
  const [form, setForm] = useState<Record<string, any>>(() => {
    const initial: Record<string, any> = {};
    for (const f of fields) {
      const fallback = f.defaultValue ?? (f.type === "checkbox" ? false : "");
      const current = row ? row[f.name] : undefined;
      const value = current ?? fallback;
      initial[f.name] = f.type === "rut" && value ? formatRut(String(value)) : value;
    }
    return initial;
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const set = (name: string, value: any) => setForm((prev) => ({ ...prev, [name]: value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");

    for (const f of fields) {
      if (f.type === "rut" && !isValidRut(String(form[f.name]))) {
        setError(`El RUT de "${f.label}" no es válido. Revisa el número y el dígito verificador.`);
        return;
      }
    }

    // Prepara los datos: vacío -> null, números -> número
    const payload: Record<string, any> = {};
    for (const f of fields) {
      const v = form[f.name];
      if (f.type === "checkbox") payload[f.name] = !!v;
      else if (v === "" || v == null) payload[f.name] = null;
      else if (f.type === "number" || f.optionsFrom) payload[f.name] = Number(v);
      else payload[f.name] = v;
    }

    setSaving(true);
    try {
      if (row) await api(`${props.endpoint}/${row.id}`, { method: "PUT", body: payload });
      else await api(props.endpoint, { method: "POST", body: payload });
      props.onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && props.onClose()}>
      <form className="modal" onSubmit={submit}>
        <div className="modal-head">
          <h2>
            {row ? "Editar" : "Nuevo"} {props.singular}
          </h2>
          <button type="button" className="btn secondary small" onClick={props.onClose}>
            ✕
          </button>
        </div>

        {error && <div className="alert">{error}</div>}

        <div className="form-grid">
          {fields.map((f) => {
            const options = f.options ?? props.fieldOptions[f.name] ?? [];
            const id = `f-${f.name}`;

            if (f.type === "checkbox") {
              return (
                <div className={`checkbox-row ${f.full ? "full" : ""}`} key={f.name}>
                  <input id={id} type="checkbox" checked={!!form[f.name]} onChange={(e) => set(f.name, e.target.checked)} />
                  <label htmlFor={id}>{f.label}</label>
                </div>
              );
            }

            return (
              <div className={f.full ? "full" : ""} key={f.name}>
                <label htmlFor={id}>
                  {f.label} {f.required && <span className="req">*</span>}
                </label>
                {f.type === "select" ? (
                  <select id={id} required={f.required} value={form[f.name] ?? ""} onChange={(e) => set(f.name, e.target.value)}>
                    {!f.required && <option value="">— Sin asignar —</option>}
                    {options.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={id}
                    type={f.type === "rut" ? "text" : f.type}
                    required={f.required}
                    placeholder={f.type === "rut" ? "12.345.678-5" : undefined}
                    value={form[f.name] ?? ""}
                    onChange={(e) => set(f.name, e.target.value)}
                    onBlur={f.type === "rut" ? () => form[f.name] && set(f.name, formatRut(String(form[f.name]))) : undefined}
                  />
                )}
              </div>
            );
          })}
        </div>

        <div className="modal-foot">
          <button type="button" className="btn secondary" onClick={props.onClose}>
            Cancelar
          </button>
          <button className="btn" disabled={saving}>
            {saving ? "Guardando..." : "Guardar"}
          </button>
        </div>
      </form>
    </div>
  );
}
