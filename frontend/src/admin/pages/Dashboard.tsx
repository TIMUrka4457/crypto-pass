import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link } from "react-router-dom";
import { Warning } from "@phosphor-icons/react";
import { ASSET_LIST, ASSET_TITLE } from "@/lib/api";
import { H, useLoad, Btn } from "../kit";

function Stat({ label, value, testid, to }: { label: string; value: any; testid: string; to?: string }) {
  const body = (
    <div className="h-full border border-white/10 bg-[#0c0c0c] p-6 hover:border-white/25">
      <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500">{label}</p>
      <p className="mt-3 font-display text-3xl font-semibold tracking-tighter tabular" data-testid={testid}>{value ?? "—"}</p>
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

export default function Dashboard() {
  const { data: s, reload } = useLoad<any>("/stats");
  if (!s) return <H title="Обзор" />;
  return (
    <div>
      <H title="Обзор"><Btn testid="dashboard-refresh" onClick={reload}>Обновить</Btn></H>
      {(s.hot_alerts.length > 0 || s.reconcile_ok === false || s.unknown_withdrawals > 0) && (
        <div className="mb-6 space-y-2" data-testid="dashboard-alerts">
          {s.reconcile_ok === false && <Alert text="Сверка журнала нашла расхождение — проверьте раздел «Журнал»" />}
          {s.unknown_withdrawals > 0 && <Alert text={`${s.unknown_withdrawals} вывод(ов) с неизвестным статусом в сети — проверьте вручную`} />}
          {s.hot_alerts.map((a: string) => <Alert key={a} text={a} />)}
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <Stat label="Пользователи" value={s.users} testid="stat-users" to="/admin/users" />
        <Stat label="DAU сегодня" value={s.dau_today} testid="stat-dau" />
        <Stat label="Выводы ждут одобрения" value={s.pending_withdrawals} testid="stat-pending-withdrawals" to="/admin/withdrawals" />
        <Stat label="AML-удержания" value={s.aml_holds} testid="stat-aml-holds" to="/admin/deposits" />
        <div className="border border-white/10 bg-[#0c0c0c] p-6 md:col-span-2 md:row-span-2">
          <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500">DAU · 14 дней</p>
          <div className="mt-4 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={s.dau_series}>
                <XAxis dataKey="day" tick={{ fill: "#71717a", fontSize: 10 }} tickFormatter={(d) => d.slice(5)} />
                <YAxis allowDecimals={false} tick={{ fill: "#71717a", fontSize: 10 }} width={30} />
                <Tooltip contentStyle={{ background: "#111", border: "1px solid #2e2e2e" }} />
                <Area type="monotone" dataKey="dau" stroke="#00FF66" fill="#00FF66" fillOpacity={0.12} strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="border border-white/10 bg-[#0c0c0c] p-6 md:col-span-2">
          <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500">Оборот · 14 дней</p>
          {ASSET_LIST.map((a) => <p key={a} className="mt-2 flex justify-between text-sm"><span className="text-zinc-400">{ASSET_TITLE[a]}</span><span className="tabular" data-testid={`stat-turnover-${a}`}>{s.turnover[a]}</span></p>)}
        </div>
        <div className="border border-white/10 bg-[#0c0c0c] p-6 md:col-span-2">
          <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500">Доход с комиссий · 14 дней</p>
          {ASSET_LIST.map((a) => <p key={a} className="mt-2 flex justify-between text-sm"><span className="text-zinc-400">{ASSET_TITLE[a]}</span><span className="tabular text-[#00FF66]" data-testid={`stat-fees-${a}`}>{s.fees[a]}</span></p>)}
        </div>
        <Stat label="Выводы в обработке" value={s.processing_withdrawals} testid="stat-processing" />
        <Stat label="Мерчанты на одобрении" value={s.pending_merchants} testid="stat-pending-merchants" to="/admin/merchants" />
        <Stat label="Сверка журнала" value={s.reconcile_ok == null ? "—" : s.reconcile_ok ? "OK" : "Ошибка"} testid="stat-reconcile" to="/admin/audit" />
      </div>
    </div>
  );
}

function Alert({ text }: { text: string }) {
  return <div className="flex items-center gap-3 border border-amber-300/40 bg-amber-300/5 px-4 py-3 text-sm text-amber-200"><Warning size={18} /> {text}</div>;
}
