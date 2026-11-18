"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/dates";

type Certificate = {
  certificate_number: string;
  issued_on: string;
  student: {
    id: number;
    full_name: string;
    rut: string;
    birth_date: string;
    gender: string | null;
    enrollment_date: string | null;
    status: string;
    guardian_name: string | null;
  };
  course: {
    id: number | null;
    name: string | null;
    level: string | null;
    year: number;
    head_teacher_name: string | null;
  };
  attendance: { year: number; marked: number; present: number; rate: number | null };
  grades: { subjects: number; average: number | null };
  signature: {
    code: string;
    algorithm: string;
    verification_url: string;
  };
};

export default function CertificadoPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<Certificate | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!params?.id) return;
    api<Certificate>(`/reports/students/${params.id}/certificate`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "No se pudo cargar el certificado"));
  }, [params?.id]);

  return (
    <>
      <div className="page-head no-print">
        <div>
          <h1>Certificado de alumno regular</h1>
          <p>Revisa los datos y luego imprime o guarda el documento como PDF.</p>
        </div>
        <div className="report-actions">
          <button className="btn secondary" onClick={() => router.push("/reportes")}>
            Volver
          </button>
          <button className="btn" disabled={!data} onClick={() => window.print()}>
            Imprimir / Guardar PDF
          </button>
        </div>
      </div>

      {error && <div className="alert no-print">{error}</div>}

      {data && (
        <div className="certificate-wrap">
          <article className="certificate">
            <div className="certificate-head">
              <div className="eyebrow">Gestión Escolar</div>
              <h1>Certificado de alumno regular</h1>
              <div className="muted small-text">N° {data.certificate_number}</div>
            </div>

            <div className="certificate-body">
              <p>
                Se certifica que <strong>{data.student.full_name}</strong>, RUT{" "}
                <strong>{data.student.rut}</strong>, nacido(a) el{" "}
                {formatDate(data.student.birth_date)}, se encuentra matriculado(a) y es
                alumno(a) regular de <strong>{data.course.name ?? "un curso sin asignar"}</strong>
                {data.course.level ? `, ${data.course.level}` : ""}, durante el año escolar{" "}
                <strong>{data.course.year}</strong>.
              </p>

              {(data.attendance.rate !== null || data.grades.average !== null) && (
                <p>
                  {data.attendance.rate !== null && (
                    <>
                      Su asistencia registrada durante el año alcanza un{" "}
                      <strong>{data.attendance.rate}%</strong> (
                      {data.attendance.marked} días con registro).
                    </>
                  )}{" "}
                  {data.grades.average !== null && (
                    <>
                      Su promedio general de notas es{" "}
                      <strong>{data.grades.average.toFixed(1)}</strong> en{" "}
                      {data.grades.subjects} {data.grades.subjects === 1 ? "asignatura" : "asignaturas"}.
                    </>
                  )}
                </p>
              )}

              <p>
                Se extiende el presente certificado a petición del interesado para los fines que
                estime convenientes.
              </p>

              <div className="certificate-meta">
                {data.student.enrollment_date && (
                  <>Fecha de matrícula: {formatDate(data.student.enrollment_date)} · </>
                )}
                {data.student.guardian_name && (
                  <>Apoderado: {data.student.guardian_name} · </>
                )}
                Emitido el {formatDate(data.issued_on)}
              </div>
            </div>

            <div className="certificate-signs">
              <div className="certificate-sign">
                {data.course.head_teacher_name ?? "Profesor jefe"}
                <br />
                Profesor(a) jefe
              </div>
              <div className="certificate-sign">
                Dirección
                <br />
                Dirección del colegio
              </div>
            </div>

            <div className="certificate-foot">
              Documento generado por el sistema de gestión escolar · {data.certificate_number}
              <div className="small-text" style={{ marginTop: 6 }}>
                Firmado electrónicamente · Código {data.signature.code} (
                {data.signature.algorithm})
              </div>
              <div className="small-text">
                Verifica la autenticidad en{" "}
                {typeof window !== "undefined" ? window.location.origin : ""}
                {data.signature.verification_url}
              </div>
            </div>
          </article>
        </div>
      )}

      {!data && !error && <p className="muted">Cargando certificado...</p>}
    </>
  );
}
