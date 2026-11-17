import { useState } from "react";
import { adminApi, ASSET_TITLE } from "@/lib/api";
import { Status } from "@/miniapp/ui";
import { H, Btn, Table, useLoad, CommentAction, dt } from "../kit";

export default function Monitoring() {
  const [tab, setTab] = useState<"checks" | "invoices">("checks");
  const [status, setStatus] = useState("active");
  const { data, reload } = useLoad<any[]>(`/${tab}?status=${status}`, [tab, status]);
  return (
    <div>
      <H title="Чеки и счета">
        <Btn testid="monitor-tab-checks" tone={tab === "checks" ? "primary" : "ghost"} onClick={() => setTab("checks")}>Чеки</Btn>
        <Btn testid="monitor-tab-invoices" tone={tab === "invoices" ? "primary" : "ghost"} onClick={() => setTab("invoices")}>Счета</Btn>
        <span className="w-4" />
        {[["active", "Активные"], ["", "Все"]].map(([k, l]) => <Btn key={k} testid={`monitor-status-${k || "all"}`} tone={status === k ? "primary" : "ghost"} onClick={() => setStatus(k)}>{l}</Btn>)}
      </H>
      {tab === "checks" ? (
        <Table testid="admin-checks-table" cols={["Создан", "Автор", "Тип", "Сумма", "Осталось", "Условия", "Истекает", "Статус", ""]}
          rows={(data || []).map((c) => [dt(c.created_at), c.creator_id, c.kind, `${c.amount_per} ${ASSET_TITLE[c.asset]}`, `${c.remaining}/${c.activations}`,
            [c.captcha && "капча", c.channels?.length && `каналы: ${c.channels.join(",")}`, c.min_account_age_days && `возраст ${c.min_account_age_days}д`, c.bind_username && `@${c.bind_username}`].filter(Boolean).join(" · ") || "—",
            dt(c.expires_at), <Status s={c.status} />,
            c.status === "active" && <CommentAction testid={`admin-check-cancel-${c.id}`} tone="danger" label="Отменить" title="Принудительная отмена (остаток вернётся автору)"
              onSubmit={(cm) => adminApi.post(`/checks/${c.id}/cancel`, { comment: cm }).then(reload)} />])} />
      ) : (
        <Table testid="admin-invoices-table" cols={["Создан", "Автор", "Мерчант", "Тип", "Сумма", "Оплат", "Получено внешн.", "Статус", ""]}
          rows={(data || []).map((i) => [dt(i.created_at), i.creator_id, i.merchant_id || "—", i.kind, `${i.amount} ${ASSET_TITLE[i.asset]}`,
            `${i.paid_count}${i.max_payments ? `/${i.max_payments}` : ""}`, i.received, <Status s={i.status} />,
            i.status === "active" && <CommentAction testid={`admin-invoice-cancel-${i.id}`} tone="danger" label="Отменить" title="Принудительная отмена счёта"
              onSubmit={(cm) => adminApi.post(`/invoices/${i.id}/cancel`, { comment: cm }).then(reload)} />])} />
      )}
    </div>
  );
}
