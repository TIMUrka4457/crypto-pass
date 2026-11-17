import { useState } from "react";
import { Warning } from "@phosphor-icons/react";
import { ASSET_LIST, ASSET_TITLE } from "@/lib/api";
import { Status } from "@/miniapp/ui";
import { H, Btn, Table, useLoad, dt, short } from "../kit";

export default function HotWallet() {
  const [n, setN] = useState(0);
  const { data: s } = useLoad<any>(`/hot-wallet${n ? "?refresh=true" : ""}`, [n]);
  return (
    <div>
      <H title="Горячий кошелёк"><Btn testid="hot-refresh" tone="primary" onClick={() => setN(n + 1)}>Обновить из сети</Btn></H>
      {!s ? <p className="text-zinc-500">Загрузка…</p> : (
        <>
          <p className="mb-4 text-xs text-zinc-500">Снимок: {dt(s.at)} {s.trx_balance && `· TRX на газ: ${s.trx_balance}`}</p>
          {s.alerts?.map((a: string) => <div key={a} data-testid="hot-alert" className="mb-2 flex items-center gap-3 border border-amber-300/40 px-4 py-3 text-sm text-amber-200"><Warning size={18} />{a}</div>)}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {ASSET_LIST.map((a) => {
              const e = s.assets?.[a] || {};
              return (
                <div key={a} className="border border-white/10 p-6">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500">{ASSET_TITLE[a]}</p>
                  <p className="mt-3 font-display text-3xl tabular" data-testid={`hot-balance-${a}`}>{e.balance ?? "нет данных"}</p>
                  <p className="mt-2 text-sm text-zinc-400">Обязательства перед пользователями: <span className="tabular text-white">{e.liabilities}</span></p>
                  <p className="text-sm text-zinc-400">Доля в горячем: <span className="tabular text-white">{e.share_pct != null ? `${e.share_pct}%` : "—"}</span> (цель 5–10%)</p>
                  <p className="text-sm text-zinc-400">Алерт ниже: {e.alert_threshold}</p>
                  <p className="mt-3 break-all text-xs text-zinc-500">{e.address}</p>
                </div>
              );
            })}
          </div>
          <h2 className="mb-3 mt-10 font-display text-lg">Свипы и газ</h2>
          <Table testid="sweeps-table" cols={["Время", "Тип", "Актив", "Сумма (минимальные ед.)", "Хеш", "Статус"]}
            rows={(s.sweeps || []).map((x: any) => [dt(x.created_at), x.kind === "gas" ? "газ" : "свип", x.asset, x.amount, short(x.tx_hash, 6), <Status s={x.status} />])} />
        </>
      )}
    </div>
  );
}

