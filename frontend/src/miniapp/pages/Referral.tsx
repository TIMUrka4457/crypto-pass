import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Copy } from "@phosphor-icons/react";
import { userApi, ASSET_LIST, ASSET_TITLE } from "@/lib/api";
import { PageHeader, Panel } from "../ui";

export default function Referral() {
  const [d, setD] = useState<any>(null);
  useEffect(() => { userApi.get("/referral").then((r) => setD(r.data)); }, []);
  if (!d) return <PageHeader title="Рефералы" />;
  return (
    <div>
      <PageHeader title="Рефералы" />
      <div className="rise space-y-8">
        <div>
          <div className="font-display text-6xl font-black tracking-tighter text-[#00FF66]" data-testid="referral-percent">{d.percent}%</div>
          <p className="mt-2 text-zinc-400">от комиссий приглашённых — сразу на ваш баланс</p>
        </div>
        <Panel>
          <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Ваша ссылка</p>
          <p className="mt-3 break-all text-sm" data-testid="referral-link">{d.link || "Бот не настроен"}</p>
          {d.link && (
            <button data-testid="referral-copy-button" onClick={() => { navigator.clipboard?.writeText(d.link); toast.success("Скопировано"); }}
              className="press mt-4 inline-flex items-center gap-2 rounded-full border border-white/15 px-4 py-2 text-sm"><Copy size={16} /> Скопировать</button>
          )}
        </Panel>
        <div className="grid grid-cols-2 gap-3">
          <Panel><p className="text-xs text-zinc-500">Приглашено</p><p className="mt-2 font-display text-3xl tabular" data-testid="referral-invited">{d.invited}</p></Panel>
          <Panel>
            <p className="text-xs text-zinc-500">Заработано</p>
            {ASSET_LIST.map((a) => <p key={a} className="mt-1 text-sm tabular">{d.earned[a]} <span className="text-zinc-500">{ASSET_TITLE[a]}</span></p>)}
          </Panel>
        </div>
      </div>
    </div>
  );
}
