import { useState } from "react";
import { adminApi, ASSET_TITLE } from "@/lib/api";
import { Status } from "@/miniapp/ui";
import { H, Table, useLoad, CommentAction, Btn, dt, short } from "../kit";

const FILTERS = [["pending_approval", "Ждут одобрения"], ["queued,signing,broadcasting,sent", "В обработке"], ["unknown", "Неизвестен"],
  ["completed", "Выполнены"], ["rejected,failed", "Отклонены/ошибки"], ["", "Все"]];

export default function Withdrawals() {
  const [status, setStatus] = useState("pending_approval");
  const { data, reload } = useLoad<any[]>(`/withdrawals?status=${status}`, [status]);
  return (
    <div>
      <H title="Очередь выводов">
        {FILTERS.map(([k, l]) => <Btn key={k} testid={`withdrawals-filter-${k.split(",")[0] || "all"}`} tone={status === k ? "primary" : "ghost"} onClick={() => setStatus(k)}>{l}</Btn>)}
      </H>
      <p className="mb-4 text-sm text-zinc-500">Выводы до лимита автоодобрения уходят в сеть сами. Статус «неизвестен» — транзакция подписана, но ответа сети нет: система не отправит её повторно, пока не убедится, что она истекла.</p>
      <Table testid="withdrawals-table" cols={["Время", "Пользователь", "Сумма", "Комиссия", "Адрес", "Хеш", "Статус", "Ошибка", ""]}
        rows={(data || []).map((w) => [dt(w.created_at), w.user_id, `${w.amount} ${ASSET_TITLE[w.asset]}`, w.fee, short(w.address, 6),
          w.tx_hash ? short(w.tx_hash, 6) : "—", <Status s={w.raw_status} />, <span className="text-xs text-zinc-500">{w.last_error || ""}</span>,
          <div className="flex gap-2">
            {w.raw_status === "pending_approval" && <CommentAction testid={`wd-approve-${w.id}`} tone="primary" label="Одобрить" title="Одобрить вывод"
              onSubmit={async (c) => { await adminApi.post(`/withdrawals/${w.id}/approve`, { comment: c }); reload(); }} />}
            {["pending_approval", "queued"].includes(w.raw_status) && <CommentAction testid={`wd-reject-${w.id}`} tone="danger" label="Отклонить" title="Отклонить и вернуть средства"
              onSubmit={async (c) => { await adminApi.post(`/withdrawals/${w.id}/reject`, { comment: c }); reload(); }} />}
            {w.raw_status === "unknown" && <CommentAction testid={`wd-failed-${w.id}`} tone="danger" label="Не прошёл → вернуть" title="Подтверждаете, что транзакции нет в эксплорере?"
              onSubmit={async (c) => { await adminApi.post(`/withdrawals/${w.id}/mark-failed`, { comment: c }); reload(); }} />}
          </div>])} />
    </div>
  );
}
