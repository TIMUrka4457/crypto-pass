import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Copy } from "@phosphor-icons/react";
import { toast } from "sonner";
import { userApi, errMsg, ASSET_TITLE } from "@/lib/api";
import { PageHeader, Panel, Segmented, Status } from "../ui";

export default function Deposit() {
  const [net, setNet] = useState("ton");
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setData(null);
    setErr("");
    userApi.get(`/deposit/${net}`).then((r) => setData(r.data)).catch((e) => setErr(errMsg(e)));
  }, [net]);
  const copy = () => {
    navigator.clipboard?.writeText(data.address);
    toast.success("Адрес скопирован");
  };
  return (
    <div>
      <PageHeader title="Пополнить" />
      <Segmented testid="deposit-network" value={net} onChange={setNet} options={[["ton", "TON · USDT"], ["tron", "TRON · TRC20"]]} />
      {err && <p className="mt-6 text-sm text-[#FF3366]" data-testid="deposit-error">{err}</p>}
      {data && (
        <div className="rise mt-8 space-y-6">
          <div className="mx-auto w-fit rounded-2xl bg-white p-4 sm:mx-0"><QRCodeSVG value={data.address} size={180} /></div>
          <Panel>
            <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Ваш адрес для депозита</p>
            <p data-testid="deposit-address" className="mt-3 break-all font-mono-num text-sm">{data.address}</p>
            <button data-testid="deposit-copy-button" onClick={copy} className="press btn-secondary mt-4 w-full sm:w-auto">
              <Copy size={16} /> Скопировать
            </button>
          </Panel>
          <ul className="space-y-2 text-sm text-zinc-400">
            <li>Принимаем: {data.assets.map((a: string) => ASSET_TITLE[a]).join(", ")}. Мемо не нужно.</li>
            <li>Зачисление после {data.confirmations} подтверждений сети.</li>
            {net === "ton" && <li>Отправляйте только оригинальный USDT (Tether). Другие jetton'ы не зачисляются.</li>}
            {net === "tron" && <li>Только USDT TRC20. TRX и другие токены не зачисляются.</li>}
          </ul>
          {data.recent.length > 0 && (
            <div className="space-y-2" data-testid="deposit-recent">
              <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Последние депозиты</p>
              {data.recent.map((d: any) => (
                <div key={d.tx_hash} className="flex items-center justify-between py-2 text-sm">
                  <span className="tabular">{d.amount} {ASSET_TITLE[d.asset]}</span>
                  <Status s={d.status} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
