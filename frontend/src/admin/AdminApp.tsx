import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { ChartLineUp, Users as UsersIcon, ArrowDown, ArrowUp, Gear, Fire, Storefront, Ticket, Megaphone, ListChecks, SignOut, CurrencyDollar } from "@phosphor-icons/react";
import { toast } from "sonner";
import { adminApi, errMsg } from "@/lib/api";
import { inp } from "./kit";
import Dashboard from "./pages/Dashboard";
import Users from "./pages/Users";
import Deposits from "./pages/Deposits";
import Withdrawals from "./pages/Withdrawals";
import Settings from "./pages/Settings";
import HotWallet from "./pages/HotWallet";
import Merchants from "./pages/Merchants";
import Monitoring from "./pages/Monitoring";
import Broadcasts from "./pages/Broadcasts";
import Audit from "./pages/Audit";
import Finance from "./pages/Finance";

const NAV = [
  ["", "Обзор", ChartLineUp], ["finance", "Финансы", CurrencyDollar], ["users", "Пользователи", UsersIcon], ["deposits", "Депозиты", ArrowDown],
  ["withdrawals", "Выводы", ArrowUp], ["hot-wallet", "Горячий кошелёк", Fire], ["merchants", "Мерчанты", Storefront],
  ["monitoring", "Чеки и счета", Ticket], ["broadcasts", "Рассылки", Megaphone], ["settings", "Настройки", Gear],
  ["audit", "Журнал и админы", ListChecks],
] as const;

export default function AdminApp({ base }: { base: string }) {
  const [me, setMe] = useState<any>(null);
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    if (!localStorage.getItem("at")) { setChecked(true); return; }
    adminApi.get("/me").then((r) => setMe(r.data)).catch(() => {}).finally(() => setChecked(true));
  }, []);
  if (!checked) return null;
  if (!me) return <Login onDone={setMe} />;
  return (
    <div className="relative z-10 flex min-h-screen bg-[#050505]" data-testid="admin-root">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-white/10 p-5 md:flex">
        <p className="font-display text-lg font-black tracking-tighter">Easy<span className="text-[#00FF66]">Crypto</span></p>
        <p className="mt-1 text-[11px] uppercase tracking-[0.2em] text-zinc-600">admin · {me.role}</p>
        <nav className="mt-8 flex flex-1 flex-col gap-1">
          {NAV.map(([to, label, Icon]) => (
            <NavLink key={to} end to={`${base}/${to}`} data-testid={`admin-nav-${to || "dashboard"}`}
              className={({ isActive }) => `press flex items-center gap-3 rounded-md px-3 py-2 text-sm ${isActive ? "bg-[#00FF66] text-black" : "text-zinc-400 hover:bg-white/5 hover:text-white"}`}>
              <Icon size={18} /> {label}
            </NavLink>
          ))}
        </nav>
        <p className="truncate text-xs text-zinc-500">{me.email}</p>
        <button data-testid="admin-logout" onClick={() => { localStorage.removeItem("at"); window.location.href = base; }}
          className="press mt-3 flex items-center gap-2 text-sm text-zinc-400 hover:text-white"><SignOut size={16} /> Выйти</button>
      </aside>
      <div className="w-full min-w-0">
        <nav className="sticky top-0 z-20 flex gap-2 overflow-x-auto border-b border-white/10 bg-[#050505]/90 p-3 backdrop-blur md:hidden">
          {NAV.map(([to, label]) => (
            <NavLink key={to} end to={`${base}/${to}`} data-testid={`admin-mnav-${to || "dashboard"}`} className={({ isActive }) => `inline-flex h-10 shrink-0 items-center whitespace-nowrap rounded-md px-4 text-sm ${isActive ? "bg-[#00FF66] text-black" : "border border-white/10 text-zinc-300"}`}>{label}</NavLink>
          ))}
        </nav>
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3 md:hidden">
          <p className="truncate text-xs text-zinc-500">{me.email} · {me.role}</p>
          <button data-testid="admin-logout-mobile" onClick={() => { localStorage.removeItem("at"); window.location.href = base; }} className="press inline-flex h-9 items-center gap-2 rounded-md border border-white/10 px-3 text-xs text-zinc-300"><SignOut size={14} /> Выйти</button>
        </div>
        <main className="p-4 sm:p-6 md:p-10">
          <Routes>
            <Route index element={<Dashboard />} />
            <Route path="finance" element={<Finance />} />
            <Route path="users" element={<Users me={me} />} />
            <Route path="deposits" element={<Deposits />} />
            <Route path="withdrawals" element={<Withdrawals />} />
            <Route path="hot-wallet" element={<HotWallet me={me} />} />
            <Route path="merchants" element={<Merchants />} />
            <Route path="monitoring" element={<Monitoring />} />
            <Route path="broadcasts" element={<Broadcasts />} />
            <Route path="settings" element={<Settings />} />
            <Route path="audit" element={<Audit me={me} />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function Login({ onDone }: { onDone: (m: any) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [cid, setCid] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const step1 = async (e: any) => {
    e.preventDefault(); setBusy(true);
    try { const r = await adminApi.post("/auth/login", { email, password }); setCid(r.data.challenge_id); toast.success("Код отправлен на почту"); }
    catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };
  const step2 = async (e: any) => {
    e.preventDefault(); setBusy(true);
    try {
      const r = await adminApi.post("/auth/verify", { challenge_id: cid, code });
      localStorage.setItem("at", r.data.token);
      onDone((await adminApi.get("/me")).data);
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };
  return (
    <div className="relative z-10 grid min-h-screen bg-[#050505] lg:grid-cols-2">
      <div className="hidden flex-col justify-end border-r border-white/10 p-14 lg:flex">
        <p className="font-display text-6xl font-black leading-none tracking-tighter">Easy<br /><span className="text-[#00FF66]">Crypto</span><br />control</p>
        <p className="mt-6 max-w-sm text-zinc-500">Вход по паролю и одноразовому коду на почту. Все действия записываются в журнал.</p>
      </div>
      <div className="flex items-center px-6 py-16 sm:px-14">
        {!cid ? (
          <form onSubmit={step1} className="w-full max-w-sm space-y-4" data-testid="admin-login-form">
            <h1 className="font-display text-2xl font-bold">Вход в админку</h1>
            <input data-testid="admin-login-email" className={`${inp} h-12 w-full`} placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <input data-testid="admin-login-password" type="password" className={`${inp} h-12 w-full`} placeholder="Пароль" value={password} onChange={(e) => setPassword(e.target.value)} />
            <button data-testid="admin-login-submit" disabled={busy} className="press h-12 w-full rounded-md bg-[#00FF66] font-display text-sm font-semibold text-black disabled:opacity-50">Продолжить</button>
          </form>
        ) : (
          <form onSubmit={step2} className="w-full max-w-sm space-y-4" data-testid="admin-otp-form">
            <h1 className="font-display text-2xl font-bold">Код из письма</h1>
            <p className="text-sm text-zinc-500">Отправили 6 цифр на {email}. Код действует 10 минут.</p>
            <input data-testid="admin-otp-input" inputMode="numeric" maxLength={6} className={`${inp} h-14 w-full text-center font-mono-num text-2xl tracking-[0.5em]`} value={code} onChange={(e) => setCode(e.target.value)} />
            <button data-testid="admin-otp-submit" disabled={busy || code.length !== 6} className="press h-12 w-full rounded-md bg-[#00FF66] font-display text-sm font-semibold text-black disabled:opacity-50">Войти</button>
          </form>
        )}
      </div>
    </div>
  );
}
