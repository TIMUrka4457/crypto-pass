import { useMemo, useState } from "react";
import { toast } from "sonner";
import { userApi, errMsg, idem, ASSET_TITLE } from "@/lib/api";
import { AssetPicker, Field, PageHeader, PrimaryButton, inputCls } from "../ui";
import { useWallet } from "../MiniApp";

export default function Transfer() {
  const { me, refresh } = useWallet();
  const [asset, setAsset] = useState("USDT_TON");
  const [to, setTo] = useState("");
  const [amount, setAmount] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const key = useMemo(() => idem(), [asset, to, amount, comment]); // eslint-disable-line react-hooks/exhaustive-deps
  const submit = async () => {
    setBusy(true);
    try {
      await userApi.post("/transfer", { to_username: to, asset, amount, comment, idempotency_key: key });
      toast.success(`Отправлено ${amount} ${ASSET_TITLE[asset]} → ${to}`);
      setAmount("");
      setComment("");
      refresh();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      <PageHeader title="Перевести" />
      <div className="space-y-6">
        <p className="text-sm text-zinc-400">Мгновенно и без комиссии — любому, кто запускал бота.</p>
        <AssetPicker value={asset} onChange={setAsset} testid="transfer-asset" />
        <p className="text-sm text-zinc-400">Доступно: <span className="tabular text-white">{me?.balances?.[asset]?.available}</span></p>
        <Field label="Получатель">
          <input data-testid="transfer-username-input" className={inputCls} value={to} onChange={(e) => setTo(e.target.value)} placeholder="@username" />
        </Field>
        <Field label="Сумма">
          <input data-testid="transfer-amount-input" inputMode="decimal" className={inputCls} value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
        </Field>
        <Field label="Комментарий">
          <input data-testid="transfer-comment-input" className={inputCls} value={comment} onChange={(e) => setComment(e.target.value)} maxLength={200} />
        </Field>
        <PrimaryButton testid="transfer-submit-button" disabled={busy || !to || !amount} onClick={submit}>
          {busy ? "Отправляем…" : "Перевести"}
        </PrimaryButton>
      </div>
    </div>
  );
}
