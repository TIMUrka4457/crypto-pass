import { useEffect, useState } from "react";
import { Warning } from "@phosphor-icons/react";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import { adminApi, errMsg, ASSET_LIST, ASSET_TITLE } from "@/lib/api";
import { Status } from "@/miniapp/ui";
import { H, Btn, Table, useLoad, dt, short, inp, CommentAction } from "../kit";

function Cold({ owner }: { owner: boolean }) {
  const { data } = useLoad<any>("/settings");
  const [c, setC] = useState<any>(null);
  const [asset, setAsset] = useState("TON");
  const [amount, setAmount] = useState("");
  useEffect(() => { if (data) setC(data.cold); }, [data]);
  if (!c) return null;
  const save = () => adminApi.put("/cold", c).then(() => toast.success("Сохранено")).catch((e) => toast.error(errMsg(e)));
  return (
    <div className="mt-10 grid grid-cols-1 gap-4 lg:grid-cols-2" data-testid="cold-section">
      <div className="space-y-3 border border-white/10 p-6 text-sm text-zinc-400">
        <p className="font-display text-lg text-white">Холодные кошельки</p>
        <p className="text-xs text-zinc-500">Переводы идут только на эти адреса. Менять их может только владелец.</p>
        {[["ton", "TON (для TON и USDT TON)"], ["tron", "TRON (для USDT TRC20)"]].map(([k, l]) => (
          <label key={k} className="block space-y-1">{l}
            <input data-testid={`cold-${k}`} disabled={!owner} className={`${inp} h-10 w-full font-mono-num text-xs`} value={c[k]} onChange={(e) => setC({ ...c, [k]: e.target.value })} />
          </label>
        ))}
        <div className="flex items-center justify-between">Автоперевод излишка
          <Switch data-testid="cold-auto" disabled={!owner} checked={c.auto} onCheckedChange={(v) => setC({ ...c, auto: v })} />
        </div>
        {[["max_pct", "Переводить, если в горячем больше, %"], ["target_pct", "Оставлять в горячем, %"]].map(([k, l]) => (
          <label key={k} className="flex items-center justify-between gap-3">{l}
            <input data-testid={`cold-${k}`} disabled={!owner} className={`${inp} h-10 w-24`} value={c[k]} onChange={(e) => setC({ ...c, [k]: e.target.value })} />
          </label>
        ))}
        {owner && <Btn testid="cold-save" tone="primary" onClick={save}>Сохранить</Btn>}
      </div>
      <div className="space-y-3 border border-white/10 p-6 text-sm text-zinc-400">
        <p className="font-display text-lg text-white">Перевести в холодный</p>
        <p className="text-xs text-zinc-500">Транзакция подписывается и отправляется автоматически. На TON-кошельке всегда остаётся 2 TON на газ.</p>
        <div className="grid grid-cols-3 gap-2">
          {ASSET_LIST.map((a) => <Btn key={a} testid={`cold-asset-${a}`} tone={a === asset ? "primary" : "ghost"} onClick={() => setAsset(a)}>{ASSET_TITLE[a]}</Btn>)}
        </div>
        <input data-testid="cold-amount" inputMode="decimal" className={`${inp} h-10 w-full`} placeholder="Сумма" value={amount} onChange={(e) => setAmount(e.target.value)} />
        {owner ? <CommentAction label="Подписать и отправить" title={`Перевести ${amount || 0} ${ASSET_TITLE[asset]} в холодный кошелёк?`} tone="primary" testid="cold-send"
          onSubmit={(comment) => adminApi.post("/cold/transfer", { asset, amount, comment }).then((r) => { setAmount(""); toast.success(`Отправлено, tx ${short(r.data.tx_hash, 6)}`); })} />
          : <p className="text-xs">Доступно только владельцу.</p>}
      </div>
    </div>
  );
}

export default function HotWallet({ me }: { me: any }) {
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
          <Cold owner={me?.role === "owner"} />
          <h2 className="mb-3 mt-10 font-display text-lg">Свипы, газ и холодные переводы</h2>
          <Table testid="sweeps-table" cols={["Время", "Тип", "Актив", "Сумма (минимальные ед.)", "Хеш", "Статус"]}
            rows={(s.sweeps || []).map((x: any) => [dt(x.created_at), x.kind === "gas" ? "газ" : x.kind === "cold" ? "→ холодный" : "свип", x.asset, x.amount, short(x.tx_hash, 6), <Status s={x.status} />])} />
        </>
      )}
    </div>
  );
}

