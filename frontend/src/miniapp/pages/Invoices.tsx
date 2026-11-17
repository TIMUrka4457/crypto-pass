import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Copy } from "@phosphor-icons/react";
import { userApi, errMsg, ASSET_TITLE } from "@/lib/api";
import { AssetPicker, Field, PageHeader, Panel, PrimaryButton, Status, inputCls } from "../ui";

export default function Invoices() {
  const [asset, setAsset] = useState("USDT_TON");
  const [kind, setKind] = useState("single");
  const [amount, setAmount] = useState("");
  const [desc, setDesc] = useState("");
  const [maxp, setMaxp] = useState("");
  const [list, setList] = useState<any[]>([]);
  const load = () => userApi.get("/invoices").then((r) => setList(r.data));
  useEffect(() => { load(); }, []);
  const create = async () => {
    try {
      const r = await userApi.post("/invoices", { asset, amount, description: desc, kind, max_payments: kind === "multi" && maxp ? Number(maxp) : null });
      if (r.data.pay_url) navigator.clipboard?.writeText(r.data.pay_url);
      toast.success("Счёт создан, ссылка скопирована");
      setAmount(""); setDesc("");
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const cancel = async (id: string) => {
    try { await userApi.post(`/invoices/${id}/cancel`); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div>
      <PageHeader title="Счета" />
      <div className="space-y-6">
        <div className="flex gap-2">
          {[["single", "Одиночный"], ["multi", "Мульти-счёт"]].map(([k, l]) => (
            <button key={k} data-testid={`invoice-kind-${k}`} onClick={() => setKind(k)}
              className={`press rounded-full border px-4 py-2 text-sm ${kind === k ? "border-[#00E5FF] text-[#00E5FF]" : "border-white/15 text-zinc-400"}`}>{l}</button>
          ))}
        </div>
        <AssetPicker value={asset} onChange={setAsset} testid="invoice-asset" />
        <Field label="Сумма"><input data-testid="invoice-amount-input" inputMode="decimal" className={inputCls} value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        {kind === "multi" && (
          <Field label="Макс. оплат" hint="Пусто — без ограничения"><input data-testid="invoice-max-input" inputMode="numeric" className={inputCls} value={maxp} onChange={(e) => setMaxp(e.target.value)} /></Field>
        )}
        <Field label="За что"><input data-testid="invoice-description-input" className={inputCls} value={desc} onChange={(e) => setDesc(e.target.value)} /></Field>
        <PrimaryButton testid="invoice-create-button" disabled={!amount} onClick={create}>Выставить счёт</PrimaryButton>
      </div>
      <div className="mt-10 space-y-3" data-testid="invoices-list">
        {list.map((i) => (
          <Panel key={i.id}>
            <div className="flex justify-between"><span className="tabular">{i.amount} {ASSET_TITLE[i.asset]}</span><Status s={i.status} testid={`invoice-status-${i.id}`} /></div>
            <p className="mt-1 text-xs text-zinc-500">{i.description} · оплат: {i.paid_count}{i.max_payments ? `/${i.max_payments}` : ""}</p>
            {i.pay_url && <button onClick={() => { navigator.clipboard?.writeText(i.pay_url); toast.success("Скопировано"); }} className="mt-2 flex items-center gap-2 truncate text-xs text-[#00E5FF]"><Copy size={14} />{i.pay_url}</button>}
            {i.status === "active" && <button data-testid={`invoice-cancel-${i.id}`} onClick={() => cancel(i.id)} className="press mt-3 rounded-full border border-[#FF3366]/40 px-4 py-1.5 text-xs text-[#FF3366]">Отменить</button>}
          </Panel>
        ))}
      </div>
    </div>
  );
}
