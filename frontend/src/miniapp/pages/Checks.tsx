import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Copy } from "@phosphor-icons/react";
import { Switch } from "@/components/ui/switch";
import { userApi, errMsg, ASSET_TITLE } from "@/lib/api";
import { AssetPicker, Field, PageHeader, Panel, PrimaryButton, Status, inputCls } from "../ui";
import { useWallet } from "../MiniApp";

const empty = { kind: "personal", amount: "", activations: "10", bind_username: "", password: "", captcha: true,
  channels: "", min_account_age_days: "", expires_in_hours: "", description: "" };

export default function Checks() {
  const { refresh } = useWallet();
  const [asset, setAsset] = useState("USDT_TON");
  const [f, setF] = useState<any>(empty);
  const [list, setList] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e?.target ? e.target.value : e });
  const load = () => userApi.get("/checks").then((r) => setList(r.data));
  useEffect(() => { load(); }, []);

  const create = async () => {
    setBusy(true);
    try {
      const body: any = { asset, kind: f.kind, amount: f.amount, description: f.description,
        expires_in_hours: f.expires_in_hours ? Number(f.expires_in_hours) : null, password: f.password || null };
      if (f.kind === "personal") body.bind_username = f.bind_username || null;
      else Object.assign(body, { activations: Number(f.activations), captcha: f.captcha,
        channels: f.channels.split(/[\s,]+/).filter(Boolean), min_account_age_days: Number(f.min_account_age_days || 0) });
      const r = await userApi.post("/checks", body);
      toast.success("Чек создан, средства заблокированы");
      if (r.data.link) navigator.clipboard?.writeText(r.data.link);
      setF(empty);
      await Promise.all([load(), refresh()]);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  const cancel = async (id: string) => {
    try {
      const r = await userApi.post(`/checks/${id}/cancel`);
      toast.success(`Отменён, возвращено ${r.data.refunded}`);
      await Promise.all([load(), refresh()]);
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div>
      <PageHeader title="Чеки" />
      <div className="space-y-6">
        <div className="flex gap-2">
          {[["personal", "Персональный"], ["multi", "Мульти-чек"]].map(([k, l]) => (
            <button key={k} data-testid={`check-kind-${k}`} onClick={() => setF({ ...f, kind: k })}
              className={`press rounded-full border px-4 py-2 text-sm ${f.kind === k ? "border-[#00E5FF] text-[#00E5FF]" : "border-white/15 text-zinc-400"}`}>{l}</button>
          ))}
        </div>
        <AssetPicker value={asset} onChange={setAsset} testid="check-asset" />
        <Field label={f.kind === "multi" ? "Сумма за одну активацию" : "Сумма"}>
          <input data-testid="check-amount-input" inputMode="decimal" className={inputCls} value={f.amount} onChange={set("amount")} placeholder="0.00" />
        </Field>
        {f.kind === "personal" ? (
          <Field label="Только для (необязательно)">
            <input data-testid="check-bind-username-input" className={inputCls} value={f.bind_username} onChange={set("bind_username")} placeholder="@username" />
          </Field>
        ) : (
          <>
            <Field label="Количество активаций">
              <input data-testid="check-activations-input" inputMode="numeric" className={inputCls} value={f.activations} onChange={set("activations")} />
            </Field>
            <Field label="Подписка на каналы" hint="Через запятую. Бот должен быть админом канала.">
              <input data-testid="check-channels-input" className={inputCls} value={f.channels} onChange={set("channels")} placeholder="@channel1, @channel2" />
            </Field>
            <Field label="Мин. возраст аккаунта, дней" hint="Оценивается по Telegram ID">
              <input data-testid="check-min-age-input" inputMode="numeric" className={inputCls} value={f.min_account_age_days} onChange={set("min_account_age_days")} placeholder="0" />
            </Field>
            <div className="flex items-center justify-between">
              <span className="text-sm text-zinc-300">Капча против ботов</span>
              <Switch data-testid="check-captcha-switch" checked={f.captcha} onCheckedChange={set("captcha")} />
            </div>
          </>
        )}
        <Field label="Пароль (необязательно)">
          <input data-testid="check-password-input" className={inputCls} value={f.password} onChange={set("password")} />
        </Field>
        <Field label="Срок действия, часов" hint="После истечения остаток вернётся вам автоматически">
          <input data-testid="check-expiry-input" inputMode="numeric" className={inputCls} value={f.expires_in_hours} onChange={set("expires_in_hours")} placeholder="без срока" />
        </Field>
        <Field label="Описание">
          <input data-testid="check-description-input" className={inputCls} value={f.description} onChange={set("description")} />
        </Field>
        <PrimaryButton testid="check-create-button" disabled={busy || !f.amount} onClick={create}>Создать чек</PrimaryButton>
      </div>
      <div className="mt-10 space-y-3" data-testid="checks-list">
        {list.map((c) => (
          <Panel key={c.id}>
            <div className="flex items-center justify-between">
              <span className="tabular">{c.amount} {ASSET_TITLE[c.asset]} {c.kind === "multi" && <span className="text-zinc-500">× {c.remaining}/{c.activations}</span>}</span>
              <Status s={c.status} testid={`check-status-${c.id}`} />
            </div>
            {c.link && (
              <button data-testid={`check-copy-${c.id}`} onClick={() => { navigator.clipboard?.writeText(c.link); toast.success("Ссылка скопирована"); }}
                className="mt-3 flex w-full items-center gap-2 truncate text-left text-xs text-[#00E5FF]"><Copy size={14} /> {c.link}</button>
            )}
            {c.status === "active" && (
              <button data-testid={`check-cancel-${c.id}`} onClick={() => cancel(c.id)} className="press mt-3 rounded-full border border-[#FF3366]/40 px-4 py-1.5 text-xs text-[#FF3366]">Отменить и вернуть</button>
            )}
          </Panel>
        ))}
      </div>
    </div>
  );
}
