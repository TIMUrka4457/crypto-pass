import { useState } from "react";
import { toast } from "sonner";
import { userApi, errMsg, ASSET_LIST, ASSET_TITLE } from "@/lib/api";
import { PageHeader, Panel, PrimaryButton, inputCls } from "../ui";
import { useWallet } from "../MiniApp";

export default function AccountSettings() {
  const { me, refresh } = useWallet();
  const [step, setStep] = useState(0);
  const [word, setWord] = useState("");
  const left = ASSET_LIST.filter((a) => me?.balances?.[a]?.available && me.balances[a].available !== "0");
  const recreate = async () => {
    try { await userApi.post("/account/recreate-addresses"); toast.success("Новые адреса появятся в «Пополнить»"); } catch (e) { toast.error(errMsg(e)); }
  };
  const del = async () => {
    try { await userApi.post("/account/delete", { confirm: word }); toast.success("Аккаунт удалён"); await refresh(); setStep(0); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div>
      <PageHeader title="Настройки" />
      <div className="space-y-4">
        <Panel>
          <p className="text-sm">Язык</p>
          <p className="mt-1 text-xs text-zinc-500">Русский. Английский появится в следующем обновлении.</p>
        </Panel>
        <Panel>
          <p className="text-sm">Новые адреса пополнения</p>
          <p className="mt-1 text-xs text-zinc-500">Старые адреса продолжат работать — переводы на них тоже зачислятся.</p>
          <button data-testid="settings-recreate-addresses" onClick={recreate} className="press btn-secondary mt-4 w-full">Выдать новые адреса</button>
        </Panel>
        <Panel className="border-[#FF3366]/30">
          <p className="text-sm text-[#FF3366]">Удалить аккаунт</p>
          {step === 0 && <button data-testid="settings-delete-start" onClick={() => setStep(1)} className="press btn-danger mt-4 w-full">Удалить аккаунт</button>}
          {step === 1 && (
            <div className="mt-3 space-y-3 text-sm">
              <p className="font-semibold">Удаление нельзя отменить.</p>
              {left.length > 0 && <p data-testid="settings-delete-balance-warning" className="text-[#FF3366]">На балансе: {left.map((a) => `${me.balances[a].available} ${ASSET_TITLE[a]}`).join(", ")}. Эти средства пропадут — сначала выведите их.</p>}
              <p className="text-zinc-400">Активные чеки и счета будут отменены, аккаунт будет заблокирован. Введите слово УДАЛИТЬ:</p>
              <input data-testid="settings-delete-confirm-input" className={inputCls} value={word} onChange={(e) => setWord(e.target.value)} />
              <PrimaryButton testid="settings-delete-confirm" disabled={word.trim().toUpperCase() !== "УДАЛИТЬ"} onClick={del}>Удалить навсегда</PrimaryButton>
              <button data-testid="settings-delete-cancel" onClick={() => { setStep(0); setWord(""); }} className="press btn-secondary w-full">Отмена</button>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
