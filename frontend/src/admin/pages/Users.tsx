import { useState } from "react";
import { adminApi, ASSET_LIST, ASSET_TITLE } from "@/lib/api";
import { Status } from "@/miniapp/ui";
import { H, Table, useLoad, CommentAction, Btn, dt, short, inp } from "../kit";

export default function Users({ me }: { me: any }) {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const { data } = useLoad<any>(`/users?q=${encodeURIComponent(query)}`, [query]);
  if (sel) return <UserDetail uid={sel} back={() => setSel(null)} me={me} />;
  return (
    <div>
      <H title="Пользователи">
        <form onSubmit={(e) => { e.preventDefault(); setQuery(q); }} className="flex gap-2">
          <input data-testid="users-search-input" className={inp} placeholder="@username, ID или имя" value={q} onChange={(e) => setQ(e.target.value)} />
          <Btn testid="users-search-button" tone="primary" onClick={() => setQuery(q)}>Найти</Btn>
        </form>
      </H>
      <p className="mb-3 text-xs text-zinc-500">Всего: {data?.total ?? "…"}</p>
      <Table testid="users-table" cols={["ID", "Username", "Имя", "Создан", "Статус", ""]}
        rows={(data?.items || []).map((u: any) => [u.id, u.username ? `@${u.username}` : "—", u.first_name, dt(u.created_at),
          u.frozen ? <Status s="rejected" /> : <span className="text-xs text-zinc-500">активен</span>,
          <Btn testid={`user-open-${u.id}`} onClick={() => setSel(u.id)}>Открыть</Btn>])} />
    </div>
  );
}

function UserDetail({ uid, back, me }: { uid: string; back: () => void; me: any }) {
  const { data: d, reload } = useLoad<any>(`/users/${uid}`, [uid]);
  const [asset, setAsset] = useState("TON");
  const [amount, setAmount] = useState("");
  const [dir, setDir] = useState("credit");
  if (!d) return <H title="…" />;
  const canAdjust = me.perms.includes("*") || me.perms.includes("adjust");
  return (
    <div>
      <H title={d.user.username ? `@${d.user.username}` : d.user.id}>
        <Btn testid="user-back" onClick={back}>← К списку</Btn>
        <CommentAction testid="user-freeze" tone="danger" label={d.user.frozen ? "Разморозить" : "Заморозить"}
          title={d.user.frozen ? "Разморозить аккаунт" : "Заморозить аккаунт"}
          onSubmit={async (c) => { await adminApi.post(`/users/${uid}/freeze`, { frozen: !d.user.frozen, comment: c }); reload(); }} />
        {canAdjust && (
          <CommentAction testid="user-adjust" tone="primary" label="Корректировка баланса" title="Ручная корректировка (через журнал)"
            extra={
              <div className="flex flex-wrap gap-2">
                <select data-testid="user-adjust-asset" className={inp} value={asset} onChange={(e) => setAsset(e.target.value)}>
                  {ASSET_LIST.map((a) => <option key={a} value={a}>{ASSET_TITLE[a]}</option>)}
                </select>
                <select data-testid="user-adjust-direction" className={inp} value={dir} onChange={(e) => setDir(e.target.value)}>
                  <option value="credit">Начислить</option><option value="debit">Списать</option>
                </select>
                <input data-testid="user-adjust-amount" className={inp} placeholder="Сумма" value={amount} onChange={(e) => setAmount(e.target.value)} />
              </div>}
            onSubmit={async (c) => { await adminApi.post(`/users/${uid}/adjust`, { asset, amount, direction: dir, comment: c }); setAmount(""); reload(); }} />
        )}
      </H>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        {ASSET_LIST.map((a) => (
          <div key={a} className="border border-white/10 p-6">
            <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500">{ASSET_TITLE[a]}</p>
            <p className="mt-2 font-display text-2xl tabular" data-testid={`user-balance-${a}`}>{d.balances[a].available}</p>
            <p className="text-xs text-amber-300 tabular">в блоке: {d.balances[a].hold}</p>
          </div>
        ))}
        <div className="border border-white/10 p-6 text-sm">
          <p className="text-zinc-500">Telegram ID: <span className="text-white">{d.user.tg_id}</span></p>
          <p className="text-zinc-500">Пригласил: <span className="text-white">{d.user.ref_by || "—"}</span></p>
          <p className="text-zinc-500">Рефералов: <span className="text-white">{d.referrals}</span></p>
          {d.addresses.map((x: any) => <p key={x.network} className="truncate text-xs text-zinc-500">{x.network}: {x.address}</p>)}
        </div>
      </div>
      <h2 className="mb-3 mt-10 font-display text-lg">История (журнал)</h2>
      <Table testid="user-history-table" cols={["Время", "Операция", "Сумма", "Счёт"]}
        rows={d.history.map((h: any) => [dt(h.created_at), h.kind_text, `${h.sign}${h.amount} ${ASSET_TITLE[h.asset]}`, h.hold ? "блок" : "доступно"])} />
      <h2 className="mb-3 mt-10 font-display text-lg">Выводы</h2>
      <Table testid="user-withdrawals-table" cols={["Время", "Сумма", "Адрес", "Статус"]}
        rows={d.withdrawals.map((w: any) => [dt(w.created_at), `${w.amount} ${ASSET_TITLE[w.asset]}`, short(w.address), <Status s={w.status} />])} />
      <h2 className="mb-3 mt-10 font-display text-lg">Депозиты</h2>
      <Table testid="user-deposits-table" cols={["Время", "Сумма", "Хеш", "Статус"]}
        rows={d.deposits.map((x: any) => [dt(x.created_at), `${x.amount} ${ASSET_TITLE[x.asset]}`, short(x.tx_hash), <Status s={x.status} />])} />
    </div>
  );
}
