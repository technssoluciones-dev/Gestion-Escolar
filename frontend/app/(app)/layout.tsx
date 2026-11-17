"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api, clearToken, getToken } from "@/lib/api";

const links = [
  { href: "/panel", label: "Panel" },
  { href: "/estudiantes", label: "Estudiantes" },
  { href: "/profesores", label: "Profesores" },
  { href: "/apoderados", label: "Apoderados" },
  { href: "/cursos", label: "Cursos" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [userName, setUserName] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api<{ full_name: string }>("/auth/me")
      .then((u) => setUserName(u.full_name))
      .catch(() => {});
  }, [router]);

  function logout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          Gestión Escolar
          <small>Panel de administración</small>
        </div>
        {links.map((l) => (
          <Link key={l.href} href={l.href} className={`nav-link ${pathname.startsWith(l.href) ? "active" : ""}`}>
            {l.label}
          </Link>
        ))}
        <div className="sidebar-footer">
          {userName ?? ""}
          <button onClick={logout}>Cerrar sesión</button>
        </div>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}
