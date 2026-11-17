import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowUp, PaperPlaneTilt, Ticket, Receipt, UsersThree, Storefront, Snowflake } from "@phosphor-icons/react";
import { userApi, ASSET_LIST, ASSET_TITLE } from "@/lib/api";
import { useWallet } from "../MiniApp";

const ACTIONS = [
  { to: "deposit", label: "Пополнить", icon: ArrowDown, accent: true },
  { to: "withdraw", label: "Вывести", icon: ArrowUp },
  { to: "transfer", label: "Перевести", icon: PaperPlaneTilt },
  { to: "checks", label: "Чеки", icon: Ticket },
];
const MORE = [
  { to: "invoices", label: "Счета", icon: Receipt },
  { to: "referral", label: "Рефералы", icon: UsersThree },
  { to: "merchant", label: "Мерчант", icon: Storefront },
];

export default function Home() {
  const { me, refresh } = useWallet();
  const [hist, setHist] = useState<any[]>([]);
  useEffect(() => {
    refresh();
    userApi.get("/history").then((r) => setHist(r.data)).catch(() => {});
  }, [refresh]);
  const b = me?.balances || {};
  return (
    <div className="pt-8">
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-[0.25em] text-zinc-500" data-testid="home-username">
          {me?.user?.username ? `@${me.user.username}` : me?.user?.first_name}
        </p>
        <span className="font-display text-xs text-[#00FF66]">EasyCrypto</span>
      </div>
      {me?.user?.frozen && (
        <div data-testid="frozen-banner" className="mt-4 flex items-center gap-2 rounded-xl border border-[#FF3366]/40 p-3 text-sm text-[#FF3366]">
          <Snowflake size={18} /> Аккаунт заморожен. Обратитесь в поддержку.
        </div>
      )}
      <div className="mt-8 space-y-5">
        {ASSET_LIST.map((a, i) => (
          <div key={a} className="rise flex items-end justify-between border-b border-white/5 pb-4" style={{ animationDelay: `${i * 70}ms` }}>
            <span className="text-sm text-zinc-400">{ASSET_TITLE[a]}</span>
            <div className="text-right">
              <div data-testid={`wallet-balance-${a}`} className="font-display text-3xl font-semibold tracking-tighter tabular">
                {b[a]?.available ?? "0"}
              </div>
              {b[a]?.hold && b[a].hold !== "0" && (
                <div className="text-xs text-amber-300 tabular" data-testid={`wallet-hold-${a}`}>в обработке: {b[a].hold}</div>
              )}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-10 grid grid-cols-4 gap-3">
        {ACTIONS.map(({ to, label, icon: Icon, accent }) => (
          <Link key={to} to={`/app/${to}`} data-testid={`action-${to}`}
            className={`press flex flex-col items-center gap-2 rounded-2xl border py-4 text-xs ${accent ? "border-[#00FF66] bg-[#00FF66] text-black" : "border-white/10 bg-[#141414] text-zinc-200 hover:border-white/30"}`}>
            <Icon size={22} weight="bold" />
            {label}
          </Link>
        ))}
      </div>
      <div className="mt-3 grid grid-cols-3 gap-3">
        {MORE.map(({ to, label, icon: Icon }) => (
          <Link key={to} to={`/app/${to}`} data-testid={`action-${to}`}
            className="press flex items-center gap-2 rounded-2xl border border-white/10 px-3 py-3 text-xs text-zinc-300 hover:border-white/30">
            <Icon size={18} /> {label}
          </Link>
        ))}
      </div>
      <h2 className="mt-12 font-display text-sm uppercase tracking-[0.2em] text-zinc-500">История</h2>
      <div className="mt-4 space-y-1" data-testid="history-list">
        {hist.length === 0 && <p className="text-sm text-zinc-600">Пока нет операций</p>}
        {hist.map((h, i) => (
          <div key={h.id + i} className="rise flex items-center justify-between py-3" style={{ animationDelay: `${Math.min(i, 10) * 40}ms` }}>
            <div>
              <div className="text-sm">{h.kind_text}</div>
              <div className="text-xs text-zinc-600">{new Date(h.created_at).toLocaleString("ru-RU")}</div>
            </div>
            <div className={`font-mono-num text-sm ${h.sign === "+" ? "text-[#00FF66]" : "text-zinc-300"}`}>
              {h.sign}{h.amount} <span className="text-zinc-500">{ASSET_TITLE[h.asset]}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
