"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/dates";

type Verification = {
  valid: boolean;
  code: string;
  certificate_number: string;
  issued_on: string;
  student_name: string | null;
  student_rut: string | null;
  course_name: string | null;
  year: number | null;
  algorithm: string;
  signed_on: string;
};

export default function VerificarCertificadoPage() {
  const params = useParams<{ code: string }>();
  const [data, setData] = useState<Verification | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!params?.code) return;
    api<Verification>(`/public/certificates/${params.code}`)
      .then(setData)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "No se pudo verificar el certificado"),
      )
      .finally(() => setLoading(false));
  }, [params?.code]);

  return (
    <main className="login-page">
      <div className="login-card">
        <h1>Verificación de certificado</h1>
        <p className="muted small-text">
          Comprueba que un certificado fue emitido por el colegio y no ha sido alterado.
        </p>

        {loading && <p className="muted">Verificando...</p>}
        {error && <div className="alert">{error}</div>}

        {data && (
          <>
            <p>
              <span className={`badge ${data.valid ? "ok" : "bad"}`}>
                {data.valid ? "Firma válida" : "Firma inválida"}
              </span>
            </p>
            <div className="table-wrap">
              <table>
                <tbody>
                  <tr>
                    <th>Código</th>
                    <td>{data.code}</td>
                  </tr>
                  <tr>
                    <th>Certificado</th>
                    <td>{data.certificate_number}</td>
                  </tr>
                  <tr>
                    <th>Estudiante</th>
                    <td>
                      {data.student_name ?? "—"}
                      {data.student_rut && (
                        <div className="muted small-text">{data.student_rut}</div>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <th>Curso</th>
                    <td>
                      {data.course_name ?? "—"}
                      {data.year ? ` (${data.year})` : ""}
                    </td>
                  </tr>
                  <tr>
                    <th>Emitido</th>
                    <td>{formatDate(data.issued_on)}</td>
                  </tr>
                  <tr>
                    <th>Firma</th>
                    <td>
                      {data.algorithm}
                      <div className="muted small-text">
                        Registrada el {formatDate(data.signed_on.slice(0, 10))}
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </>
        )}

        <p style={{ marginTop: 16 }}>
          <Link href="/login">Ir al ingreso</Link>
        </p>
      </div>
    </main>
  );
}
