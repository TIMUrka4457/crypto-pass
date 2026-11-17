import { lazy, Suspense, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { API } from "@/lib/api";

const AdminApp = lazy(() => import("@/admin/AdminApp"));

export default function AdminGate() {
  const { key = "" } = useParams();
  const [state, setState] = useState<"check" | "ok" | "no">(key.length >= 20 ? "check" : "no");
  useEffect(() => {
    if (key.length < 20) { setState("no"); return; }
    axios.get(`${API}/p/${encodeURIComponent(key)}`)
      .then(() => { sessionStorage.setItem("pk", key); setState("ok"); })
      .catch(() => setState("no"));
  }, [key]);
  useEffect(() => {
    const m = document.createElement("meta");
    m.name = "robots"; m.content = "noindex,nofollow";
    document.head.appendChild(m);
    return () => { m.remove(); };
  }, []);
  if (state === "check") return null;
  if (state === "no") return <NotFound />;
  return <Suspense fallback={null}><AdminApp base={`/${key}`} /></Suspense>;
}

export function NotFound() {
  return (
    <div className="relative z-10 flex min-h-screen flex-col items-start justify-center px-6 sm:px-14" data-testid="not-found">
      <p className="font-display text-6xl font-black tracking-tighter text-[#00FF66]">404</p>
      <p className="mt-4 text-zinc-400">Страница не найдена.</p>
      <a href="/" data-testid="not-found-home" className="press mt-8 inline-flex h-12 items-center rounded-full border border-white/15 px-6 text-sm hover:border-white/40">На главную</a>
    </div>
  );
}
