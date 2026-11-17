import { useState } from "react";
import { toast } from "sonner";
import { adminApi, errMsg } from "@/lib/api";
import { H, Btn, Table, useLoad, dt, inp } from "../kit";

export default function Audit({ me }: { me: any }) {
  const { data } = useLoad<any[]>("/audit");
  const admins = useLoad<any[]>("/admins");
  const [rec, setRec] = useState<any>(null);
  const [f, setF] = useState({ email: "", password: "", role: "support" });
  const isOwner = me.role === "owner";
  const check = async () => { try { setRec((await adminApi.get("/ledger/reconcile")).data); } catch (e) { toast.error(errMsg(e)); } };
  const add = async () => {
    try { await adminApi.post("/admins", f); toast.success("Админ создан"); setF({ email: "", password: "", role: "support" }); admins.reload(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div>
      <H title="Журнал и админы"><Btn testid="reconcile-button" tone="primary" onClick={check}>Сверить журнал проводок</Btn></H>
      {rec && (
        <div data-testid="reconcile-result" className={`mb-6 border p-4 text-sm ${rec.ok ? "border-[#00FF66]/40 text-[#00FF66]" : "border-[#FF3366]/40 text-[#FF3366]"}`}>
          {rec.ok ? `Сверка OK: ${rec.accounts} счетов, сумма проводок совпадает с балансами` : `Расхождения: ${JSON.stringify(rec.mismatches)} ${JSON.stringify(rec.negative_user_balances)}`}
        </div>
      )}
      <h2 className="mb-3 font-display text-lg">Администраторы</h2>
      <Table testid="admins-table" cols={["Email", "Роль", "Активен", ""]}
        rows={(admins.data || []).map((a) => [a.email, a.role, a.active ? "да" : "нет",
          isOwner && a.role !== "owner" ? <Btn testid={`admin-toggle-${a.id}`} tone="danger" onClick={() => adminApi.post(`/admins/${a.id}/active`, { active: !a.active }).then(admins.reload)}>{a.active ? "Отключить" : "Включить"}</Btn> : null])} />
      {isOwner && (
        <div className="mt-4 flex flex-wrap gap-2" data-testid="admin-create-form">
          <input data-testid="admin-create-email" className={inp} placeholder="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
          <input data-testid="admin-create-password" type="password" className={inp} placeholder="пароль (10+ символов)" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          <select data-testid="admin-create-role" className={inp} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
            <option value="support">Поддержка (просмотр, заморозка, отмена чеков)</option><option value="admin">Админ</option>
          </select>
          <Btn testid="admin-create-submit" tone="primary" onClick={add}>Добавить</Btn>
        </div>
      )}
      <h2 className="mb-3 mt-10 font-display text-lg">Журнал действий</h2>
      <Table testid="audit-table" cols={["Время", "Админ", "Действие", "Объект", "Комментарий", "Детали", "IP"]}
        rows={(data || []).map((a) => [dt(a.at), a.admin_email, a.action, <span className="block max-w-[180px] truncate">{a.target}</span>, a.comment || "—",
          <span className="block max-w-xs truncate text-xs text-zinc-500">{JSON.stringify(a.details)}</span>, a.ip])} />
    </div>
  );
}
