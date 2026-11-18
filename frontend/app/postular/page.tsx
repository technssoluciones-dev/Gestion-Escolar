"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { formatRut, isValidRut } from "@/lib/rut";

type Course = {
  id: number;
  name: string;
  level: string | null;
  year: number;
  capacity: number;
  vacancies: number;
};

type Form = {
  applicant_rut: string;
  first_name: string;
  last_name: string;
  birth_date: string;
  gender: string;
  email: string;
  phone: string;
  address: string;
  guardian_first_name: string;
  guardian_last_name: string;
  guardian_rut: string;
  guardian_email: string;
  guardian_phone: string;
  course_id: string;
};

const emptyForm: Form = {
  applicant_rut: "",
  first_name: "",
  last_name: "",
  birth_date: "",
  gender: "",
  email: "",
  phone: "",
  address: "",
  guardian_first_name: "",
  guardian_last_name: "",
  guardian_rut: "",
  guardian_email: "",
  guardian_phone: "",
  course_id: "",
};

export default function PostularPage() {
  const router = useRouter();
  const [courses, setCourses] = useState<Course[]>([]);
  const [form, setForm] = useState<Form>(emptyForm);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api<Course[]>("/public/courses").then(setCourses).catch(() => {});
  }, []);

  function set<K extends keyof Form>(key: K, value: Form[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!isValidRut(form.applicant_rut)) {
      setError("El RUT del postulante no es válido.");
      return;
    }
    if (!form.first_name.trim() || !form.last_name.trim()) {
      setError("Indica el nombre y apellido del postulante.");
      return;
    }
    if (!form.guardian_first_name.trim() || !form.guardian_last_name.trim()) {
      setError("Indica el nombre y apellido del apoderado.");
      return;
    }
    if (!form.guardian_email.trim() && !form.guardian_phone.trim()) {
      setError("Deja un correo o teléfono de contacto del apoderado.");
      return;
    }
    if (form.guardian_rut && !isValidRut(form.guardian_rut)) {
      setError("El RUT del apoderado no es válido.");
      return;
    }
    setSaving(true);
    try {
      const data = await api<{ token: string }>("/public/admissions", {
        method: "POST",
        body: {
          ...form,
          gender: form.gender || null,
          email: form.email || null,
          phone: form.phone || null,
          address: form.address || null,
          guardian_rut: form.guardian_rut || null,
          guardian_email: form.guardian_email || null,
          guardian_phone: form.guardian_phone || null,
          course_id: form.course_id ? Number(form.course_id) : null,
        },
      });
      router.push(`/postular/${data.token}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo enviar la postulación");
      setSaving(false);
    }
  }

  return (
    <div className="login-page" style={{ alignItems: "flex-start", paddingTop: 32 }}>
      <div className="card" style={{ width: "100%", maxWidth: 820 }}>
        <div className="page-head" style={{ marginBottom: 12 }}>
          <div>
            <h1>Postulación en línea</h1>
            <p>Completa los datos del postulante y de su apoderado.</p>
          </div>
          <Link className="btn secondary small" href="/login">
            Volver al ingreso
          </Link>
        </div>

        {error && <div className="alert">{error}</div>}

        <form onSubmit={submit}>
          <h2>Postulante</h2>
          <div className="form-grid">
            <div>
              <label htmlFor="applicant_rut">RUT *</label>
              <input
                id="applicant_rut"
                value={form.applicant_rut}
                onChange={(e) => set("applicant_rut", formatRut(e.target.value))}
                placeholder="12.345.678-5"
                required
              />
            </div>
            <div>
              <label htmlFor="birth_date">Fecha de nacimiento *</label>
              <input
                id="birth_date"
                type="date"
                value={form.birth_date}
                onChange={(e) => set("birth_date", e.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="first_name">Nombres *</label>
              <input
                id="first_name"
                value={form.first_name}
                onChange={(e) => set("first_name", e.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="last_name">Apellidos *</label>
              <input
                id="last_name"
                value={form.last_name}
                onChange={(e) => set("last_name", e.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="gender">Género</label>
              <select
                id="gender"
                value={form.gender}
                onChange={(e) => set("gender", e.target.value)}
              >
                <option value="">Sin especificar</option>
                <option value="F">Femenino</option>
                <option value="M">Masculino</option>
                <option value="O">Otro</option>
              </select>
            </div>
            <div>
              <label htmlFor="email">Correo del postulante</label>
              <input
                id="email"
                type="email"
                value={form.email}
                onChange={(e) => set("email", e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="phone">Teléfono</label>
              <input
                id="phone"
                value={form.phone}
                onChange={(e) => set("phone", e.target.value)}
              />
            </div>
            <div className="full">
              <label htmlFor="address">Dirección</label>
              <input
                id="address"
                value={form.address}
                onChange={(e) => set("address", e.target.value)}
              />
            </div>
          </div>

          <h2 style={{ marginTop: 18 }}>Apoderado</h2>
          <div className="form-grid">
            <div>
              <label htmlFor="guardian_first_name">Nombres *</label>
              <input
                id="guardian_first_name"
                value={form.guardian_first_name}
                onChange={(e) => set("guardian_first_name", e.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="guardian_last_name">Apellidos *</label>
              <input
                id="guardian_last_name"
                value={form.guardian_last_name}
                onChange={(e) => set("guardian_last_name", e.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="guardian_rut">RUT</label>
              <input
                id="guardian_rut"
                value={form.guardian_rut}
                onChange={(e) => set("guardian_rut", formatRut(e.target.value))}
                placeholder="12.345.678-5"
              />
            </div>
            <div>
              <label htmlFor="guardian_email">Correo</label>
              <input
                id="guardian_email"
                type="email"
                value={form.guardian_email}
                onChange={(e) => set("guardian_email", e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="guardian_phone">Teléfono</label>
              <input
                id="guardian_phone"
                value={form.guardian_phone}
                onChange={(e) => set("guardian_phone", e.target.value)}
              />
            </div>
          </div>

          <h2 style={{ marginTop: 18 }}>Curso al que postula</h2>
          <div className="form-grid">
            <div className="full">
              <label htmlFor="course_id">Curso</label>
              <select
                id="course_id"
                value={form.course_id}
                onChange={(e) => set("course_id", e.target.value)}
              >
                <option value="">Sin curso definido</option>
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.name} ({course.year}) · {course.vacancies} cupo(s) disponible(s)
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="toolbar" style={{ marginTop: 18 }}>
            <button className="btn" disabled={saving}>
              {saving ? "Enviando..." : "Enviar postulación"}
            </button>
            <span className="muted small-text">
              Después podrás adjuntar documentos con tu número de seguimiento.
            </span>
          </div>
        </form>
      </div>
    </div>
  );
}
