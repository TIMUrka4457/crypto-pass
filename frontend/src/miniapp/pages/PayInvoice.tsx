import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { QRCodeSVG } from "qrcode.react";
import { userApi, errMsg, ASSET_TITLE } from "@/lib/api";
import { PageHeader, Panel, PrimaryButton, Status } from "../ui";
import { useWallet } from "../MiniApp";

export default function PayInvoice() {
  const { code } = useParams();
  const { me, refresh } = useWallet();
  const [inv, setInv] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => userApi.get(`/invoices/view/${code}`).then((r) => setInv(r.data)).catch((e) => setErr(errMsg(e)));
  useEffect(() => { load(); }, [code]); // eslint-disable-line react-hooks/exhaustive-deps
  const pay = async () => {
    setBusy(true);
    try {
      await userApi.post(`/invoices/pay/${code}`);
      toast.success("Оплачено");
      await Promise.all([load(), refresh()]);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div>
      <PageHeader title="Оплата счёта" />
      {err && <p className="text-[#FF3366]" data-testid="invoice-error">{err}</p>}
      {inv && (
        <div className="rise space-y-6">
          <p className="text-sm text-zinc-400">Получатель: <span className="text-white" data-testid="invoice-recipient">{inv.recipient}</span></p>
          <div className="font-display text-5xl font-black tracking-tighter tabular" data-testid="invoice-amount">{inv.amount}</div>
          <p className="text-zinc-400">{ASSET_TITLE[inv.asset]} {inv.description && `· ${inv.description}`}</p>
          <Status s={inv.status} testid="invoice-status" />
          {inv.already_paid ? <p className="text-sm text-[#00FF66]" data-testid="invoice-already-paid">Вы оплатили этот счёт</p> : inv.status === "active" && (
            <>
              <p className="text-sm text-zinc-400">На балансе: <span className="tabular">{me?.balances?.[inv.asset]?.available}</span></p>
              <PrimaryButton testid="invoice-pay-button" disabled={busy} onClick={pay}>Оплатить с баланса</PrimaryButton>
            </>
          )}
          {inv.external_address && !inv.already_paid && (
            <Panel>
              <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Или переводом с внешнего кошелька</p>
              <div className="mt-4 w-fit rounded-xl bg-white p-3"><QRCodeSVG value={inv.external_address} size={140} /></div>
              <p className="mt-3 break-all font-mono-num text-xs" data-testid="invoice-external-address">{inv.external_address}</p>
              <p className="mt-2 text-xs text-zinc-500">Отправьте ровно {inv.amount} {ASSET_TITLE[inv.asset]}. Счёт закроется после подтверждений сети.</p>
            </Panel>
          )}
        </div>
      )}
    </div>
  );
}
