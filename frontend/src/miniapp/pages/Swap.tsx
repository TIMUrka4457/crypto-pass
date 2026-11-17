import { useEffect, useMemo, useState } from "react";
import { ArrowsDownUp } from "@phosphor-icons/react";
import { toast } from "sonner";
import { userApi, errMsg, idem, ASSET_LIST, ASSET_TITLE } from "@/lib/api";
import { AssetPicker, Field, PageHeader, Panel, PrimaryButton, inputCls } from "../ui";
import { useWallet } from "../MiniApp";

export default function Swap() {
  const { me, refresh } = useWallet();
  const [from, setFrom] = useState("TON");
  const [to, setTo] = useState("USDT_TON");
  const [amount, setAmount] = useState("");
  const [q, setQ] = useState<any>(null);
  const [qErr, setQErr] = useState("");
  const [busy, setBusy] = useState(false);
  const key = useMemo(() => idem(), [from, to, amount]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    setQ(null); setQErr("");
    if (!amount || isNaN(Number(amount)) || from === to) return;
    const t = setTimeout(() => {
      userApi.get("/swap/quote", { params: { from_asset: from, to_asset: to, amount } }).then((r) => setQ(r.data)).catch((e) => setQErr(errMsg(e)));
    }, 400);
    return () => clearTimeout(t);
  }, [from, to, amount]);
  const pickFrom = (a: string) => { setFrom(a); if (a === to) setTo(ASSET_LIST.find((x) => x !== a) as string); };
  const flip = () => { setFrom(to); setTo(from); };
  const submit = async () => {
    setBusy(true);
    try {
      const r = await userApi.post("/swap", { from_asset: from, to_asset: to, amount, min_receive: q.receive, idempotency_key: key });
      toast.success(`Получено ${r.data.receive} ${ASSET_TITLE[to]}`);
      setAmount("");
      await refresh();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div>
      <PageHeader title="Обмен" />
      <div className="space-y-6">
        <Field label="Отдаёте" hint={`Доступно: ${me?.balances?.[from]?.available ?? "0"} ${ASSET_TITLE[from]}`}>
          <AssetPicker value={from} onChange={pickFrom} testid="swap-from" />
        </Field>
        <input data-testid="swap-amount-input" inputMode="decimal" className={inputCls} value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
        <button type="button" data-testid="swap-flip" onClick={flip} className="press btn-secondary mx-auto flex"><ArrowsDownUp size={18} /> Поменять местами</button>
        <Field label="Получаете">
          <AssetPicker value={to} onChange={setTo} assets={ASSET_LIST.filter((a) => a !== from)} testid="swap-to" />
        </Field>
        <Panel>
          {qErr && <p className="text-sm text-[#FF3366]" data-testid="swap-error">{qErr}</p>}
          {!qErr && (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-zinc-400">Получите</span><span data-testid="swap-receive" className="font-display text-xl tabular">{q ? `${q.receive} ${ASSET_TITLE[to]}` : "—"}</span></div>
              <div className="flex justify-between text-zinc-500"><span>Курс</span><span className="tabular">{q ? `1 ${ASSET_TITLE[from]} = ${q.rate} ${ASSET_TITLE[to]}` : "—"}</span></div>
              <div className="flex justify-between text-zinc-500"><span>Комиссия обмена</span><span className="tabular">{q ? `${q.fee} (${q.fee_pct}%)` : "—"}</span></div>
            </div>
          )}
        </Panel>
        <PrimaryButton testid="swap-submit-button" disabled={busy || !q} onClick={submit}>{busy ? "Меняем…" : "Обменять"}</PrimaryButton>
      </div>
    </div>
  );
}
