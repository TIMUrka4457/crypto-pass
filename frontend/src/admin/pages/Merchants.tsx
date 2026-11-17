import { useState } from "react";
import { adminApi } from "@/lib/api";
import { Status } from "@/miniapp/ui";
import { H, Table, useLoad, CommentAction, dt, inp } from "../kit";

export default function Merchants() {
  const { data, reload } = useLoad<any[]>("/merchants");
  const [fee, setFee] = useState("");
  const post = (id: string, body: any) => adminApi.post(`/merchants/${id}`, body).then(reload);
  return (
    <div>
      <H title="Мерчанты" />
      <Table testid="merchants-table" cols={["Создан", "Название", "Сайт", "Владелец", "Комиссия", "Ключи", "Статус", ""]}
        rows={(data || []).map((m) => [dt(m.created_at), m.name, m.website || "—", m.user_id, m.fee_pct ? `${m.fee_pct}%` : "по умолч.", m.active_keys, <Status s={m.status} />,
          <div className="flex gap-2">
            {m.status !== "approved" && <CommentAction testid={`merchant-approve-${m.id}`} tone="primary" label="Одобрить" title="Одобрить мерчанта"
              onSubmit={(c) => post(m.id, { status: "approved", comment: c })} />}
            {m.status === "approved" && <CommentAction testid={`merchant-suspend-${m.id}`} tone="danger" label="Приостановить" title="Приостановить мерчанта"
              onSubmit={(c) => post(m.id, { status: "suspended", comment: c })} />}
            {m.status === "pending" && <CommentAction testid={`merchant-reject-${m.id}`} tone="danger" label="Отклонить" title="Отклонить заявку"
              onSubmit={(c) => post(m.id, { status: "rejected", comment: c })} />}
            <CommentAction testid={`merchant-fee-${m.id}`} label="Ставка" title="Индивидуальная комиссия, %"
              extra={<input data-testid={`merchant-fee-input-${m.id}`} className={inp} placeholder="например 0.8" value={fee} onChange={(e) => setFee(e.target.value)} />}
              onSubmit={(c) => post(m.id, { fee_pct: fee, comment: c })} />
            {m.active_keys > 0 && <CommentAction testid={`merchant-revoke-${m.id}`} tone="danger" label="Отозвать ключи" title="Отозвать все API-ключи"
              onSubmit={(c) => adminApi.post(`/merchants/${m.id}/revoke-keys`, { comment: c }).then(reload)} />}
          </div>])} />
    </div>
  );
}
