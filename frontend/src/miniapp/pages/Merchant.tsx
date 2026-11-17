import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Copy, Key, Trash } from "@phosphor-icons/react";
import { userApi, errMsg } from "@/lib/api";
import { Field, PageHeader, Panel, PrimaryButton, Status, inputCls } from "../ui";

export default function Merchant() {
  const [m, setM] = useState<any>(undefined);
  const [name, setName] = useState("");
  const [site, setSite] = useState("");
  const [hook, setHook] = useState("");
  const [newKey, setNewKey] = useState("");
  const load = () => userApi.get("/merchant").then((r) => { setM(r.data.merchant); setHook(r.data.merchant?.webhook_url || ""); });
  useEffect(() => { load(); }, []);
  const act = async (fn: () => Promise<any>, ok: string) => {
    try { await fn(); toast.success(ok); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  if (m === undefined) return <PageHeader title="Кабинет мерчанта" />;
  if (!m) return (
    <div>
      <PageHeader title="Кабинет мерчанта" />
      <div className="space-y-6">
        <p className="text-zinc-400">Принимайте оплату криптой в магазине, боте или игре через API: инвойсы, выплаты и вебхуки с подписью.</p>
        <Field label="Название проекта"><input data-testid="merchant-name-input" className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Сайт или бот"><input data-testid="merchant-site-input" className={inputCls} value={site} onChange={(e) => setSite(e.target.value)} /></Field>
        <PrimaryButton testid="merchant-apply-button" disabled={name.length < 2} onClick={() => act(() => userApi.post("/merchant/apply", { name, website: site }), "Заявка отправлена")}>Подать заявку</PrimaryButton>
      </div>
    </div>
  );
  return (
    <div>
      <PageHeader title="Кабинет мерчанта" />
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-xl" data-testid="merchant-name">{m.name}</h2>
          <Status s={m.status} testid="merchant-status" />
        </div>
        {m.status === "pending" && <p className="text-sm text-zinc-400">Заявка на рассмотрении. После одобрения появятся API-ключи.</p>}
        {m.status === "approved" && (
          <>
            <p className="text-sm text-zinc-400">Комиссия с платежа: <span className="text-white">{m.fee_pct ?? "по умолчанию"}%</span></p>
            <Panel>
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">API-ключи</p>
                <button data-testid="merchant-new-key-button" onClick={async () => {
                  try { const r = await userApi.post("/merchant/keys", { label: "" }); setNewKey(r.data.api_key); load(); } catch (e) { toast.error(errMsg(e)); }
                }} className="press inline-flex h-11 items-center gap-2 rounded-full bg-[#00FF66] px-5 text-sm font-semibold text-black"><Key size={16} /> Новый ключ</button>
              </div>
              {newKey && (
                <div className="mt-4 rounded-xl border border-amber-300/40 p-3" data-testid="merchant-new-key">
                  <p className="text-xs text-amber-300">Сохраните ключ — он показывается один раз</p>
                  <p className="mt-2 break-all font-mono-num text-xs">{newKey}</p>
                  <button onClick={() => { navigator.clipboard?.writeText(newKey); toast.success("Скопировано"); }} className="mt-2 inline-flex items-center gap-1 text-xs text-[#00E5FF]"><Copy size={14} /> Копировать</button>
                </div>
              )}
              <div className="mt-4 space-y-2">
                {m.keys.map((k: any) => (
                  <div key={k.id} className="flex items-center justify-between text-sm">
                    <span className={`font-mono-num ${k.revoked ? "text-zinc-600 line-through" : ""}`}>{k.prefix}</span>
                    {!k.revoked && <button data-testid={`merchant-revoke-${k.id}`} onClick={() => act(() => userApi.delete(`/merchant/keys/${k.id}`), "Ключ отозван")} className="text-[#FF3366]"><Trash size={16} /></button>}
                  </div>
                ))}
              </div>
            </Panel>
            <Panel>
              <Field label="URL для вебхуков" hint="Подпись: X-Signature = HMAC-SHA256(secret, timestamp + '.' + body)">
                <input data-testid="merchant-webhook-input" className={inputCls} value={hook} onChange={(e) => setHook(e.target.value)} placeholder="https://shop.example/webhook" />
              </Field>
              <p className="mt-3 break-all text-xs text-zinc-500">Секрет: <span className="font-mono-num text-zinc-300" data-testid="merchant-webhook-secret">{m.webhook_secret}</span></p>
              <button data-testid="merchant-webhook-save" onClick={() => act(() => userApi.put("/merchant/webhook", { url: hook }), "Сохранено")} className="press btn-secondary mt-4">Сохранить</button>
            </Panel>
            {m.webhooks.length > 0 && (
              <div className="space-y-2" data-testid="merchant-webhooks">
                <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Последние вебхуки</p>
                {m.webhooks.map((h: any) => (
                  <div key={h.id} className="flex justify-between text-xs"><span className="text-zinc-400">{new Date(h.created_at).toLocaleString("ru-RU")} · {h.attempts} попыт.</span><Status s={h.status} /></div>
                ))}
              </div>
            )}
            <a href="/#api" className="block text-sm text-[#00E5FF]" data-testid="merchant-docs-link">Документация API →</a>
          </>
        )}
      </div>
    </div>
  );
}
