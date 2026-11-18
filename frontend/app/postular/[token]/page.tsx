"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, apiUpload } from "@/lib/api";
import { formatDate } from "@/lib/dates";

type Document = {
  id: number;
  name: string;
  filename: string;
  size: number;
  uploaded_at: string;
};

type Admission = {
  token: string;
  status: string;
  applicant_name: string;
  course_name: string | null;
  year: number;
  application_date: string;
  documents: Document[];
};

const STATUS_LABELS: Record<string, string> = {
  postulada: "Postulada",
  en_revision: "En revisión",
  aceptada: "Aceptada",
  rechazada: "Rechazada",
  matriculada: "Matriculada",
};

function statusTone(status: string): string {
  if (status === "aceptada" || status === "matriculada") return "ok";
  if (status === "rechazada") return "bad";
  if (status === "en_revision") return "warn";
  return "none";
}

export default function SeguimientoPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;
  const [admission, setAdmission] = useState<Admission | null>(null);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [docName, setDocName] = useState("");
  const [docFile, setDocFile] = useState<File | null>(null);
  const [inputKey, setInputKey] = useState(0);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(() => {
    api<Admission>(`/public/admissions/${token}`)
      .then(setAdmission)
      .catch((e) =>
        setLoadError(e instanceof Error ? e.message : "No se pudo cargar la postulación"),
      );
  }, [token]);

  useEffect(load, [load]);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!docName.trim() || !docFile) {
      setError("Indica un nombre y selecciona un archivo.");
      return;
    }
    setUploading(true);
    setError("");
    setNotice("");
    try {
      const data = new FormData();
      data.append("name", docName.trim());
      data.append("file", docFile);
      await apiUpload(`/public/admissions/${token}/documents`, data);
      setNotice("Documento adjuntado a tu postulación.");
      setDocName("");
      setDocFile(null);
      setInputKey((k) => k + 1);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo subir el documento");
    } finally {
      setUploading(false);
    }
  }

  if (loadError) {
    return (
      <div className="login-page" style={{ alignItems: "flex-start", paddingTop: 32 }}>
        <div className="card" style={{ width: "100%", maxWidth: 720 }}>
          <div className="alert">{loadError}</div>
          <Link className="btn" href="/postular">
            Hacer una postulación
          </Link>
        </div>
      </div>
    );
  }
  if (!admission) return <p className="muted">Cargando postulación...</p>;

  return (
    <div className="login-page" style={{ alignItems: "flex-start", paddingTop: 32 }}>
      <div className="card" style={{ width: "100%", maxWidth: 820 }}>
        <div className="page-head" style={{ marginBottom: 12 }}>
          <div>
            <h1>Postulación recibida</h1>
            <p>Guarda este enlace para seguir tu postulación y adjuntar documentos.</p>
          </div>
          <Link className="btn secondary small" href="/login">
            Ir al ingreso
          </Link>
        </div>

        <div className="mini-stats">
          <div className="mini-stat">
            <div className="n">
              <span className={`badge ${statusTone(admission.status)}`}>
                {STATUS_LABELS[admission.status] ?? admission.status}
              </span>
            </div>
            <div className="l">Estado de la postulación</div>
          </div>
          <div className="mini-stat">
            <div className="n">{admission.applicant_name}</div>
            <div className="l">
              {admission.course_name ?? "Sin curso definido"} · {admission.year}
            </div>
          </div>
          <div className="mini-stat">
            <div className="n">{admission.documents.length}</div>
            <div className="l">Documento(s) adjunto(s)</div>
          </div>
        </div>

        <p className="muted small-text">
          Número de seguimiento: <strong>{admission.token}</strong> · Postulada el{" "}
          {formatDate(admission.application_date)}
        </p>

        {error && <div className="alert">{error}</div>}
        {notice && <div className="notice">{notice}</div>}

        <h2 style={{ marginTop: 18 }}>Documentos</h2>
        {admission.documents.length === 0 ? (
          <p className="muted">Aún no has adjuntado documentos.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Documento</th>
                  <th>Archivo</th>
                  <th>Subido</th>
                </tr>
              </thead>
              <tbody>
                {admission.documents.map((doc) => (
                  <tr key={doc.id}>
                    <td>
                      <strong>{doc.name}</strong>
                    </td>
                    <td>{doc.filename}</td>
                    <td>{formatDate(doc.uploaded_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <form onSubmit={upload} style={{ marginTop: 14 }}>
          <div className="form-grid">
            <div>
              <label htmlFor="doc-name">Nombre del documento</label>
              <input
                id="doc-name"
                value={docName}
                onChange={(e) => setDocName(e.target.value)}
                placeholder="Certificado de nacimiento"
              />
            </div>
            <div>
              <label htmlFor="doc-file">Archivo (PDF, JPG o PNG, máx. 5 MB)</label>
              <input
                key={inputKey}
                id="doc-file"
                type="file"
                accept=".pdf,.jpg,.jpeg,.png"
                onChange={(e) => setDocFile(e.target.files?.[0] ?? null)}
              />
            </div>
          </div>
          <div className="toolbar" style={{ marginTop: 12 }}>
            <button className="btn" disabled={uploading}>
              {uploading ? "Subiendo..." : "Adjuntar documento"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
