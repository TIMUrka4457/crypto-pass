import { useState } from "react";
import { adminApi, ASSET_TITLE } from "@/lib/api";
import { Status } from "@/miniapp/ui";
import { H, Table, useLoad, CommentAction, Btn, dt, short, inp } from "../kit";

const FILTERS = [["aml_hold", "AML-удержание"], ["confirming", "Подтверждаются"], ["credited", "Зачислены"], ["rejected", "Отклонены"], ["", "Все"]];

export default function Deposits() {
  const [status, setStatus] = useState("aml_hold");
  const { data, reload } = useLoad<any[]>(`/deposits?status=${status}`, [status]);
  const bl = useLoad<any[]>("/aml/blocklist");
  const [addr, setAddr] = useState("");
  const [note, setNote] = useState("");
  return (
    <div>
      <H title="Депозиты">
        {FILTERS.map(([k, l]) => <Btn key={k} testid={`deposits-filter-${k || "all"}`} tone={status === k ? "primary" : "ghost"} onClick={() => setStatus(k)}>{l}</Btn>)}
      </H>
      <Table testid="deposits-table" cols={["Время", "Сеть", "Сумма", "От кого", "Хеш", "AML", "Статус", ""]}
        rows={(data || []).map((d) => [dt(d.created_at), d.network, `${d.amount} ${ASSET_TITLE[d.asset]}`, short(d.from, 6), short(d.tx_hash, 8),
          d.aml ? <span className={d.aml.risk == null ? "text-amber-300" : d.aml.risk >= 0.5 ? "text-[#FF3366]" : "text-zinc-400"}>
            {d.aml.risk == null ? `нет данных (${d.aml.error || d.aml.source})` : `${Math.round(d.aml.risk * 100)}% · ${d.aml.source}`}</span> : "—",
          <Status s={d.status} />,
          d.status === "aml_hold" ? (
            <div className="flex gap-2">
              <CommentAction testid={`deposit-credit-${d.id}`} tone="primary" label="Зачислить" title="Зачислить вручную"
                onSubmit={async (c) => { await adminApi.post(`/deposits/${encodeURIComponent(d.id)}/credit`, { comment: c, unblock_sweep: false }); reload(); }} />
              <CommentAction testid={`deposit-reject-${d.id}`} tone="danger" label="Отклонить" title="Отклонить депозит (средства остаются замороженными)"
                onSubmit={async (c) => { await adminApi.post(`/deposits/${encodeURIComponent(d.id)}/reject`, { comment: c }); reload(); }} />
            </div>) : null])} />
      <h2 className="mb-3 mt-12 font-display text-lg">Чёрный список адресов</h2>
      <p className="mb-4 text-sm text-zinc-500">Депозиты с этих адресов сразу уходят на ручную проверку, даже если AML-провайдер их пропустил.</p>
      <div className="mb-4 flex flex-wrap gap-2">
        <input data-testid="blocklist-address-input" className={`${inp} min-w-[320px]`} placeholder="Адрес" value={addr} onChange={(e) => setAddr(e.target.value)} />
        <input data-testid="blocklist-note-input" className={inp} placeholder="Причина" value={note} onChange={(e) => setNote(e.target.value)} />
        <Btn testid="blocklist-add-button" tone="primary" disabled={!addr} onClick={async () => { await adminApi.post("/aml/blocklist", { address: addr, note }); setAddr(""); setNote(""); bl.reload(); }}>Добавить</Btn>
      </div>
      <Table testid="blocklist-table" cols={["Адрес", "Причина", "Добавил", ""]}
        rows={(bl.data || []).map((b) => [b.address, b.note, b.admin, <Btn testid={`blocklist-del-${b.id}`} tone="danger" onClick={async () => { await adminApi.delete(`/aml/blocklist/${b.id}`); bl.reload(); }}>Удалить</Btn>])} />
    </div>
  );
}
