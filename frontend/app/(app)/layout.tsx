"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api, clearToken, getToken } from "@/lib/api";

type Role = "admin" | "secretaria" | "profesor" | "apoderado" | "estudiante";

const STAFF: Role[] = ["admin", "secretaria", "profesor"];
const MANAGEMENT: Role[] = ["admin", "secretaria"];

const links: { href: string; label: string; roles: Role[] }[] = [
  { href: "/panel", label: "Panel", roles: STAFF },
  { href: "/asistencia", label: "Asistencia", roles: STAFF },
  { href: "/notas", label: "Notas", roles: STAFF },
  { href: "/evaluaciones", label: "Evaluaciones", roles: STAFF },
  { href: "/reportes", label: "Reportes", roles: STAFF },
  { href: "/utp", label: "UTP", roles: STAFF },
  { href: "/estudiantes", label: "Estudiantes", roles: MANAGEMENT },
  { href: "/profesores", label: "Profesores", roles: MANAGEMENT },
  { href: "/apoderados", label: "Apoderados", roles: MANAGEMENT },
  { href: "/cursos", label: "Cursos", roles: MANAGEMENT },
  { href: "/asignaturas", label: "Asignaturas", roles: MANAGEMENT },
  { href: "/horarios", label: "Horarios", roles: MANAGEMENT },
  { href: "/admisiones", label: "Admisiones", roles: MANAGEMENT },
  { href: "/pagos", label: "Pagos", roles: MANAGEMENT },
  { href: "/notificaciones", label: "Notificaciones", roles: MANAGEMENT },
  { href: "/usuarios", label: "Usuarios", roles: ["admin"] },
];

const ROLE_LABELS: Record<Role, string> = {
  admin: "Administrador",
  secretaria: "Secretaría",
  profesor: "Profesor",
  apoderado: "Apoderado",
  estudiante: "Estudiante",
};

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<{ full_name: string; role: Role } | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api<{ full_name: string; role: Role }>("/auth/me")
      .then((u) => {
        if (u.role === "apoderado" || u.role === "estudiante") {
          router.replace("/portal");
          return;
        }
        setUser(u);
      })
      .catch(() => {});
  }, [router]);

  function logout() {
    clearToken();
    router.replace("/login");
  }

  const visible = user ? links.filter((l) => l.roles.includes(user.role)) : [];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          Gestión Escolar
          <small>{user ? ROLE_LABELS[user.role] : "Panel"}</small>
        </div>
        {visible.map((l) => (
          <Link key={l.href} href={l.href} className={`nav-link ${pathname.startsWith(l.href) ? "active" : ""}`}>
            {l.label}
          </Link>
        ))}
        <div className="sidebar-footer">
          {user?.full_name ?? ""}
          <button onClick={logout}>Cerrar sesión</button>
        </div>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}
