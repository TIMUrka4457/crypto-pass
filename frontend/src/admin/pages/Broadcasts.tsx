import { useState } from "react";
import { toast } from "sonner";
import { adminApi, errMsg } from "@/lib/api";
import { Status } from "@/miniapp/ui";
import { H, Btn, Table, useLoad, dt } from "../kit";

export default function Broadcasts() {
  const { data, reload } = useLoad<any[]>("/broadcasts");
  const [text, setText] = useState("");
  const send = async () => {
    if (!window.confirm("Отправить сообщение всем пользователям бота?")) return;
    try { await adminApi.post("/broadcasts", { text }); setText(""); toast.success("Рассылка поставлена в очередь"); reload(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div>
      <H title="Рассылки" />
      <div className="max-w-2xl space-y-3">
        <textarea data-testid="broadcast-text" rows={5} maxLength={4000} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Текст сообщения для всех пользователей бота" className="w-full rounded-md border border-white/10 bg-black p-4 text-sm" />
        <Btn testid="broadcast-send" tone="primary" disabled={!text.trim()} onClick={send}>Отправить всем</Btn>
      </div>
      <h2 className="mb-3 mt-10 font-display text-lg">История</h2>
      <Table testid="broadcasts-table" cols={["Создана", "Автор", "Текст", "Доставлено", "Ошибок", "Статус"]}
        rows={(data || []).map((b) => [dt(b.created_at), b.admin_email, <span className="block max-w-xs truncate">{b.text}</span>, b.sent, b.failed, <Status s={b.status} />])} />
    </div>
  );
}
