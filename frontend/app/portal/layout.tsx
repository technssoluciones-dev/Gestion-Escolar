"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "@/lib/api";

type Me = { full_name: string; role: "apoderado" | "estudiante" };

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api<Me>("/portal/me")
      .then(setMe)
      .catch((e) => {
        if (e?.status === 403) router.replace("/panel");
      });
  }, [router]);

  function logout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <div className="portal-shell">
      <header className="portal-bar">
        <div className="brand portal-brand">
          Gestión Escolar
          <small>Portal de familias</small>
        </div>
        <div className="portal-user">
          {me?.full_name}
          <button className="btn small secondary" onClick={logout}>
            Cerrar sesión
          </button>
        </div>
      </header>
      <main className="portal-content">{children}</main>
    </div>
  );
}
