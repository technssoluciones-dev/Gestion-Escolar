"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

type Role = "admin" | "secretaria" | "profesor" | "apoderado" | "estudiante";

type User = {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  guardian_id: number | null;
  student_id: number | null;
  teacher_id: number | null;
  guardian_name: string | null;
  student_name: string | null;
  teacher_name: string | null;
};

type Option = { id: number; full_name: string; course?: { name: string } | null };

const ROLE_OPTIONS: { value: Role; label: string }[] = [
  { value: "admin", label: "Administrador" },
  { value: "secretaria", label: "Secretaría" },
  { value: "profesor", label: "Profesor" },
  { value: "apoderado", label: "Apoderado (portal)" },
  { value: "estudiante", label: "Estudiante (portal)" },
];

const ROLE_LABELS: Record<Role, string> = {
  admin: "Administrador",
  secretaria: "Secretaría",
  profesor: "Profesor",
  apoderado: "Apoderado",
  estudiante: "Estudiante",
};

function roleTone(role: Role): string {
  if (role === "admin") return "info";
  if (role === "secretaria") return "ok";
  if (role === "profesor") return "warn";
  return "none";
}

function roleLink(user: User): string {
  if (user.role === "apoderado") return user.guardian_name ?? "—";
  if (user.role === "estudiante") return user.student_name ?? "—";
  if (user.role === "profesor") return user.teacher_name ?? "Sin vincular";
  return "—";
}

type FormState = {
  full_name: string;
  email: string;
  password: string;
  role: Role;
  is_active: boolean;
  guardian_id: string;
  student_id: string;
  teacher_id: string;
};

function emptyForm(): FormState {
  return {
    full_name: "",
    email: "",
    password: "",
    role: "secretaria",
    is_active: true,
    guardian_id: "",
    student_id: "",
    teacher_id: "",
  };
}

function formFrom(user: User): FormState {
  return {
    full_name: user.full_name,
    email: user.email,
    password: "",
    role: user.role,
    is_active: user.is_active,
    guardian_id: user.guardian_id ? String(user.guardian_id) : "",
    student_id: user.student_id ? String(user.student_id) : "",
    teacher_id: user.teacher_id ? String(user.teacher_id) : "",
  };
}

export default function UsuariosPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [guardians, setGuardians] = useState<Option[]>([]);
  const [students, setStudents] = useState<Option[]>([]);
  const [teachers, setTeachers] = useState<Option[]>([]);
  const [me, setMe] = useState<{ id: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("todos");

  const [modal, setModal] = useState<{ mode: "new" | "edit"; item?: User } | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [userResult, guardianResult, studentResult, teacherResult, meResult] =
        await Promise.all([
          api<{ items: User[] }>("/users?limit=200"),
          api<{ items: Option[] }>("/guardians?limit=200"),
          api<{ items: Option[] }>("/students?limit=200"),
          api<{ items: Option[] }>("/teachers?limit=200"),
          api<{ id: number }>("/auth/me"),
        ]);
      setUsers(userResult.items);
      setGuardians(guardianResult.items);
      setStudents(studentResult.items);
      setTeachers(teacherResult.items);
      setMe(meResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron cargar los usuarios");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return users.filter((user) => {
      if (roleFilter !== "todos" && user.role !== roleFilter) return false;
      if (!term) return true;
      return (
        user.full_name.toLowerCase().includes(term) ||
        user.email.toLowerCase().includes(term)
      );
    });
  }, [users, query, roleFilter]);

  function openNew() {
    setError("");
    setNotice("");
    setForm(emptyForm());
    setModal({ mode: "new" });
  }

  function openEdit(user: User) {
    setError("");
    setNotice("");
    setForm(formFrom(user));
    setModal({ mode: "edit", item: user });
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!form.full_name.trim() || !form.email.trim()) {
      setError("Completa el nombre y el correo.");
      return;
    }
    if (modal?.mode === "new" && form.password.length < 8) {
      setError("La contraseña debe tener al menos 8 caracteres.");
      return;
    }
    if (form.password && form.password.length < 8) {
      setError("La contraseña debe tener al menos 8 caracteres.");
      return;
    }
    if (form.role === "apoderado" && !form.guardian_id) {
      setError("Selecciona el apoderado asociado a la cuenta.");
      return;
    }
    if (form.role === "estudiante" && !form.student_id) {
      setError("Selecciona el estudiante asociado a la cuenta.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const body: Record<string, unknown> = {
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        role: form.role,
        is_active: form.is_active,
        guardian_id: form.role === "apoderado" ? Number(form.guardian_id) : null,
        student_id: form.role === "estudiante" ? Number(form.student_id) : null,
        teacher_id: form.role === "profesor" && form.teacher_id ? Number(form.teacher_id) : null,
      };
      if (form.password) body.password = form.password;
      if (modal?.mode === "edit" && modal.item) {
        await api(`/users/${modal.item.id}`, { method: "PUT", body });
        setNotice("Usuario actualizado.");
      } else {
        await api("/users", { method: "POST", body });
        setNotice("Usuario creado.");
      }
      setModal(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar el usuario");
    } finally {
      setSaving(false);
    }
  }

  async function remove(user: User) {
    if (!window.confirm(`¿Eliminar la cuenta de ${user.full_name}?`)) return;
    setError("");
    setNotice("");
    try {
      await api(`/users/${user.id}`, { method: "DELETE" });
      setNotice("Usuario eliminado.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo eliminar el usuario");
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Usuarios</h1>
          <p>Cuentas del panel y del portal de familias, con sus permisos.</p>
        </div>
        <button className="btn" onClick={openNew}>
          Nuevo usuario
        </button>
      </div>

      {error && <div className="alert">{error}</div>}
      {notice && <div className="notice">{notice}</div>}

      <div className="filters">
        <div>
          <label htmlFor="q">Buscar</label>
          <input
            id="q"
            type="search"
            placeholder="Nombre o correo..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="role-filter">Rol</label>
          <select
            id="role-filter"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          >
            <option value="todos">Todos los roles</option>
            {ROLE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Usuario</th>
              <th>Rol</th>
              <th>Vínculo</th>
              <th>Estado</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filtered.map((user) => (
              <tr key={user.id}>
                <td>
                  <strong>{user.full_name}</strong>
                  <div className="muted small-text">{user.email}</div>
                </td>
                <td>
                  <span className={`badge ${roleTone(user.role)}`}>
                    {ROLE_LABELS[user.role]}
                  </span>
                </td>
                <td>
                  {roleLink(user)}
                  {(user.role === "apoderado" || user.role === "estudiante") && (
                    <div className="muted small-text">Portal de familias</div>
                  )}
                </td>
                <td>
                  <span className={`badge ${user.is_active ? "ok" : "bad"}`}>
                    {user.is_active ? "Activo" : "Inactivo"}
                  </span>
                </td>
                <td>
                  <div className="row-actions">
                    <button className="btn small secondary" onClick={() => openEdit(user)}>
                      Editar
                    </button>
                    <button
                      className="btn small danger"
                      onClick={() => remove(user)}
                      disabled={user.id === me?.id}
                      title={user.id === me?.id ? "No puedes eliminar tu propio usuario" : ""}
                    >
                      Eliminar
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="empty">Cargando usuarios...</div>}
        {!loading && filtered.length === 0 && (
          <div className="empty">No hay usuarios que coincidan con los filtros.</div>
        )}
      </div>

      <p className="muted small-text" style={{ marginTop: 10 }}>
        Los apoderados y estudiantes entran al portal con su correo y contraseña. Los profesores
        pueden marcar asistencia y notas; la secretaría administra estudiantes, cursos, admisiones
        y pagos.
      </p>

      {modal && (
        <div className="overlay">
          <div className="modal">
            <div className="modal-head">
              <h2>{modal.mode === "edit" ? "Editar usuario" : "Nuevo usuario"}</h2>
              <button className="btn secondary small" onClick={() => setModal(null)}>
                Cerrar
              </button>
            </div>
            <form onSubmit={save}>
              <div className="form-grid">
                <div>
                  <label htmlFor="full-name">
                    Nombre completo <span className="req">*</span>
                  </label>
                  <input
                    id="full-name"
                    type="text"
                    value={form.full_name}
                    onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="email">
                    Correo <span className="req">*</span>
                  </label>
                  <input
                    id="email"
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="password">
                    Contraseña {modal.mode === "new" ? <span className="req">*</span> : null}
                  </label>
                  <input
                    id="password"
                    type="password"
                    minLength={8}
                    placeholder={modal.mode === "edit" ? "Dejar en blanco para mantener" : "Mínimo 8 caracteres"}
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    required={modal.mode === "new"}
                  />
                </div>
                <div>
                  <label htmlFor="role">Rol</label>
                  <select
                    id="role"
                    value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
                  >
                    {ROLE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>

                {form.role === "apoderado" && (
                  <div className="full">
                    <label htmlFor="guardian">
                      Apoderado <span className="req">*</span>
                    </label>
                    <select
                      id="guardian"
                      value={form.guardian_id}
                      onChange={(e) => setForm({ ...form, guardian_id: e.target.value })}
                      required
                    >
                      <option value="">Selecciona un apoderado</option>
                      {guardians.map((guardian) => (
                        <option key={guardian.id} value={guardian.id}>
                          {guardian.full_name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {form.role === "estudiante" && (
                  <div className="full">
                    <label htmlFor="student">
                      Estudiante <span className="req">*</span>
                    </label>
                    <select
                      id="student"
                      value={form.student_id}
                      onChange={(e) => setForm({ ...form, student_id: e.target.value })}
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
                )}

                {form.role === "profesor" && (
                  <div className="full">
                    <label htmlFor="teacher">Ficha de profesor (opcional)</label>
                    <select
                      id="teacher"
                      value={form.teacher_id}
                      onChange={(e) => setForm({ ...form, teacher_id: e.target.value })}
                    >
                      <option value="">Sin vincular</option>
                      {teachers.map((teacher) => (
                        <option key={teacher.id} value={teacher.id}>
                          {teacher.full_name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <div className="checkbox-row full">
                  <input
                    id="active"
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                  />
                  <label htmlFor="active">Cuenta activa (puede iniciar sesión)</label>
                </div>
              </div>

              <div className="modal-foot">
                <button type="button" className="btn secondary" onClick={() => setModal(null)}>
                  Cancelar
                </button>
                <button className="btn" disabled={saving}>
                  {saving ? "Guardando..." : "Guardar usuario"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
