import { ReactNode, useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { ArrowRight, List, X } from "@phosphor-icons/react";
import { userApi } from "@/lib/api";

export function useBot() {
  const [bot, setBot] = useState<string | null>(null);
  useEffect(() => { userApi.get("/config").then((r) => setBot(r.data.bot_username)).catch(() => {}); }, []);
  return bot;
}

const NAV = [["/how-it-works", "Как это работает"], ["/fees", "Комиссии"], ["/business", "Для бизнеса"], ["/faq", "Вопросы"]];

export function BotButton({ bot, label, testid }: { bot: string | null; label?: string; testid: string }) {
  if (!bot) return null;
  return (
    <a data-testid={testid} href={`https://t.me/${bot}`} className="press inline-flex h-14 items-center gap-3 rounded-full bg-[#00FF66] px-7 font-display text-sm font-semibold text-black hover:bg-[#33ff85]">
      {label || `Открыть @${bot}`} <ArrowRight weight="bold" />
    </a>
  );
}

export function Site({ children }: { children: ReactNode }) {
  const bot = useBot();
  const [open, setOpen] = useState(false);
  return (
    <div className="relative z-10 min-h-screen">
      <header className="sticky top-0 z-30 border-b border-white/10 bg-[#0a0a0a]/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 sm:px-10">
          <Link to="/" data-testid="site-logo" className="font-display text-lg font-black tracking-tighter">Easy<span className="text-[#00FF66]">Crypto</span></Link>
          <nav className="hidden items-center gap-7 md:flex">
            {NAV.map(([to, l]) => <NavLink key={to} to={to} data-testid={`site-nav-${to.slice(1)}`} className={({ isActive }) => `text-sm ${isActive ? "text-[#00FF66]" : "text-zinc-400 hover:text-white"}`}>{l}</NavLink>)}
            {bot && <a href={`https://t.me/${bot}`} data-testid="site-nav-bot" className="press inline-flex h-10 items-center rounded-full border border-[#00FF66]/60 px-5 text-sm text-[#00FF66] hover:bg-[#00FF66]/10">Открыть бота</a>}
          </nav>
          <button data-testid="site-menu-toggle" onClick={() => setOpen(!open)} className="press inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/15 md:hidden">{open ? <X size={18} /> : <List size={18} />}</button>
        </div>
        {open && (
          <nav className="grid gap-1 border-t border-white/10 px-5 py-3 md:hidden">
            {NAV.map(([to, l]) => <Link key={to} to={to} onClick={() => setOpen(false)} className="flex h-12 items-center text-zinc-300">{l}</Link>)}
          </nav>
        )}
      </header>
      <main className="mx-auto max-w-6xl px-5 pb-24 sm:px-10">{children}</main>
      <footer className="border-t border-white/10">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-10 text-sm text-zinc-500 sm:flex-row sm:items-center sm:justify-between sm:px-10">
          <p>© {new Date().getFullYear()} EasyCrypto · кошелёк и платёжный шлюз в Telegram</p>
          <div className="flex flex-wrap gap-5">{NAV.map(([to, l]) => <Link key={to} to={to} className="hover:text-white">{l}</Link>)}</div>
        </div>
      </footer>
    </div>
  );
}

export function PageTitle({ kicker, title, children }: { kicker: string; title: ReactNode; children?: ReactNode }) {
  return (
    <section className="rise pt-16 sm:pt-24">
      <p className="text-xs uppercase tracking-[0.25em] text-[#00FF66]">{kicker}</p>
      <h1 className="mt-5 max-w-4xl font-display text-4xl font-black leading-[0.95] tracking-tighter sm:text-5xl lg:text-6xl">{title}</h1>
      {children && <div className="mt-8 max-w-2xl text-zinc-400">{children}</div>}
    </section>
  );
}

export function Card({ n, title, text }: { n?: string; title: string; text: ReactNode }) {
  return (
    <div className="h-full border border-white/10 bg-[#0c0c0c] p-6 transition-colors hover:border-white/25">
      {n && <span className="font-mono-num text-xs text-[#00E5FF]">{n}</span>}
      <p className="mt-3 font-display text-base font-semibold">{title}</p>
      <p className="mt-3 text-sm leading-relaxed text-zinc-400">{text}</p>
    </div>
  );
}
