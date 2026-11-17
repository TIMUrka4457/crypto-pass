import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import { adminApi, errMsg, ASSET_LIST, ASSET_TITLE } from "@/lib/api";
import { H, Btn, useLoad, inp } from "../kit";

const FIELDS: [string, string][] = [["withdraw_fee", "Мин. комиссия вывода"], ["deposit_fee", "Комиссия пополнения"], ["withdraw_min", "Мин. вывод"], ["per_op_limit", "Лимит за операцию"],
  ["daily_limit", "Лимит в сутки"], ["auto_approve_limit", "Автоодобрение до"], ["sweep_threshold", "Порог свипа"], ["hot_alert", "Алерт горячего ниже"]];
const FEATURES: [string, string][] = [["transfers", "Внутренние переводы"], ["checks", "Чеки"], ["invoices", "Счета"], ["merchant", "Платёжный шлюз"], ["referral", "Рефералка"], ["swap", "Обмен"]];

export default function Settings() {
  const { data } = useLoad<any>("/settings");
  const [s, setS] = useState<any>(null);
  useEffect(() => { if (data) setS(JSON.parse(JSON.stringify(data))); }, [data]);
  if (!s) return <H title="Настройки" />;
  const upd = (path: string[], v: any) => {
    const n = JSON.parse(JSON.stringify(s));
    let o = n;
    path.slice(0, -1).forEach((k) => (o = o[k]));
    o[path[path.length - 1]] = v;
    setS(n);
  };
  const save = async () => {
    try { await adminApi.put("/settings", s); toast.success("Сохранено и записано в журнал"); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div>
      <H title="Настройки"><Btn testid="settings-save" tone="primary" onClick={save}>Сохранить</Btn></H>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {["ton", "tron"].map((n) => (
          <div key={n} className="border border-white/10 p-6">
            <div className="flex items-center justify-between">
              <p className="font-display text-lg uppercase">{n}</p>
              <Switch data-testid={`settings-network-${n}`} checked={s.networks[n].enabled} onCheckedChange={(v) => upd(["networks", n, "enabled"], v)} />
            </div>
            <label className="mt-4 flex items-center justify-between text-sm text-zinc-400">Подтверждений
              <input data-testid={`settings-conf-${n}`} className={`${inp} w-24`} value={s.networks[n].confirmations} onChange={(e) => upd(["networks", n, "confirmations"], Number(e.target.value) || 0)} />
            </label>
          </div>
        ))}
      </div>
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {ASSET_LIST.map((a) => (
          <div key={a} className="border border-white/10 p-6">
            <p className="font-display text-lg">{ASSET_TITLE[a]}</p>
            {[["deposit_enabled", "Депозиты"], ["withdraw_enabled", "Выводы"]].map(([k, l]) => (
              <div key={k} className="mt-3 flex items-center justify-between text-sm text-zinc-400">{l}
                <Switch data-testid={`settings-${a}-${k}`} checked={s.assets[a][k]} onCheckedChange={(v) => upd(["assets", a, k], v)} />
              </div>
            ))}
            {FIELDS.map(([k, l]) => (
              <label key={k} className="mt-3 flex items-center justify-between gap-3 text-sm text-zinc-400">{l}
                <input data-testid={`settings-${a}-${k}`} className={`${inp} w-28`} value={s.assets[a][k]} onChange={(e) => upd(["assets", a, k], e.target.value)} />
              </label>
            ))}
          </div>
        ))}
      </div>
      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="border border-white/10 p-6">
          <p className="font-display text-lg">Функции</p>
          {FEATURES.map(([k, l]) => (
            <div key={k} className="mt-3 flex items-center justify-between text-sm text-zinc-400">{l}
              <Switch data-testid={`settings-feature-${k}`} checked={s.features[k]} onCheckedChange={(v) => upd(["features", k], v)} />
            </div>
          ))}
        </div>
        <div className="space-y-3 border border-white/10 p-6 text-sm text-zinc-400">
          <p className="font-display text-lg text-white">Комиссии, AML, антиабуз</p>
          {[[["merchant_fee_pct"], "Комиссия мерчанта, %"], [["referral_pct"], "Доля реферала от комиссий, %"], [["aml", "risk_threshold"], "AML: порог риска (0–1)"],
            [["check_claims_per_minute"], "Попыток активации чека в минуту"], [["gas", "ton_jetton_sweep"], "Газ на свип jetton, TON"], [["gas", "tron_trx_topup"], "TRX на энергию для свипа"],
            [["fees", "gas_margin_pct"], "Запас к цене газа, %"], [["fees", "profit_usdt"], "Наценка на вывод USDT, $"],
            [["fees", "ton_jetton_gas"], "Газ вывода USDT TON, TON"], [["fees", "tron_energy_existing"], "Энергия TRC20 (адрес с USDT)"],
            [["fees", "tron_energy_new"], "Энергия TRC20 (новый адрес)"], [["fees", "hot_trx_alert"], "Алерт: TRX на газ ниже"],
            [["swap", "fee_pct"], "Обмен: спред, %"], [["swap", "min_usd"], "Обмен: минимум, $"], [["swap", "max_usd"], "Обмен: максимум, $"]].map(([p, l]: any) => (
            <label key={p.join(".")} className="flex items-center justify-between gap-3">{l}
              <input data-testid={`settings-${p.join("-")}`} className={`${inp} w-28`} value={p.reduce((o: any, k: string) => o[k], s)} onChange={(e) => upd(p, e.target.value)} />
            </label>
          ))}
          <div className="flex items-center justify-between">Динамическая комиссия USDT (по цене газа)
            <Switch data-testid="settings-fees-dynamic" checked={s.fees.dynamic} onCheckedChange={(v) => upd(["fees", "dynamic"], v)} />
          </div>
          <div className="flex items-center justify-between">AML-проверка входящих
            <Switch data-testid="settings-aml-enabled" checked={s.aml.enabled} onCheckedChange={(v) => upd(["aml", "enabled"], v)} />
          </div>
          <p className="text-xs text-zinc-600">Если AML-провайдер не ответил, депозит уходит на ручную проверку. Комиссия вывода USDT = реальная стоимость газа по рыночной цене + запас + наценка, но не ниже минимума. Комиссия пополнения — не больше 10% суммы.</p>
        </div>
      </div>
    </div>
  );
}
