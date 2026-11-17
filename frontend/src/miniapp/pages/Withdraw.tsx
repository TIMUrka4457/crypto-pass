import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { userApi, errMsg, idem, ASSET_TITLE } from "@/lib/api";
import { AssetPicker, Field, PageHeader, PrimaryButton, Status, inputCls } from "../ui";
import { useWallet } from "../MiniApp";

export default function Withdraw() {
  const { me, config, refresh } = useWallet();
  const [asset, setAsset] = useState("TON");
  const [address, setAddress] = useState("");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [list, setList] = useState<any[]>([]);
  const key = useMemo(() => idem(), [asset, address, amount]); // eslint-disable-line react-hooks/exhaustive-deps
  const cfg = config?.assets?.[asset] || {};
  const [fee, setFee] = useState<string | null>(null);
  useEffect(() => {
    setFee(null);
    const t = setTimeout(() => {
      userApi.get("/withdrawals/quote", { params: { asset, address } }).then((r) => setFee(r.data.fee)).catch(() => setFee(cfg.withdraw_fee));
    }, 400);
    return () => clearTimeout(t);
  }, [asset, address]); // eslint-disable-line react-hooks/exhaustive-deps
  const feeNum = Number(fee ?? cfg.withdraw_fee ?? 0);
  const load = () => userApi.get("/withdrawals").then((r) => setList(r.data));
  useEffect(() => { load(); }, []);

  const submit = async () => {
    setBusy(true);
    try {
      const r = await userApi.post("/withdrawals", { asset, address, amount, idempotency_key: key });
      toast.success(r.data.status_text);
      setAmount("");
      await Promise.all([refresh(), load()]);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  const total = amount && !isNaN(Number(amount)) ? (Number(amount) + feeNum).toFixed(6).replace(/\.?0+$/, "") : "—";
  return (
    <div>
      <PageHeader title="Вывести" />
      <div className="space-y-6">
        <AssetPicker value={asset} onChange={setAsset} testid="withdraw-asset" />
        <p className="text-sm text-zinc-400">Доступно: <span className="tabular text-white" data-testid="withdraw-available">{me?.balances?.[asset]?.available}</span> {ASSET_TITLE[asset]}</p>
        <Field label="Адрес получателя">
          <input data-testid="withdraw-address-input" className={inputCls} value={address} onChange={(e) => setAddress(e.target.value)} placeholder={asset === "USDT_TRC20" ? "T…" : "UQ… / EQ…"} />
        </Field>
        <Field label="Сумма" hint={`Минимум ${cfg.withdraw_min} · лимит ${cfg.per_op_limit} за раз, ${cfg.daily_limit} в сутки`}>
          <input data-testid="withdraw-amount-input" inputMode="decimal" className={inputCls} value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
        </Field>
        <div className="flex justify-between border-t border-white/10 pt-4 text-sm">
          <span className="text-zinc-400">Комиссия сети</span>
          <span className="tabular" data-testid="withdraw-fee">{fee ?? "…"} {ASSET_TITLE[asset]}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-zinc-400">Спишется с баланса</span>
          <span className="tabular" data-testid="withdraw-total">{total} {ASSET_TITLE[asset]}</span>
        </div>
        <PrimaryButton testid="withdraw-submit-button" disabled={busy || !address || !amount || !cfg.withdraw_enabled} onClick={submit}>
          {cfg.withdraw_enabled === false ? "Вывод временно отключён" : busy ? "Отправляем…" : "Вывести"}
        </PrimaryButton>
        <p className="text-xs text-zinc-500">Суммы выше {cfg.auto_approve_limit} проходят ручную проверку. Если сеть недоступна, вывод встанет в очередь — статус будет «в обработке».</p>
      </div>
      <div className="mt-10 space-y-3" data-testid="withdraw-list">
        {list.map((w) => (
          <div key={w.id} className="rounded-xl border border-white/10 p-4 text-sm">
            <div className="flex justify-between"><span className="tabular">{w.amount} {ASSET_TITLE[w.asset]}</span><Status s={w.status} testid={`withdraw-status-${w.id}`} /></div>
            <div className="mt-1 truncate text-xs text-zinc-500">{w.address}</div>
            {w.explorer && <a className="mt-1 block truncate text-xs text-[#00E5FF]" href={w.explorer} target="_blank" rel="noreferrer">{w.tx_hash}</a>}
          </div>
        ))}
      </div>
    </div>
  );
}
