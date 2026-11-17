import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { Ticket } from "@phosphor-icons/react";
import { userApi, errMsg, ASSET_TITLE } from "@/lib/api";
import { Field, PageHeader, PrimaryButton, Status, inputCls } from "../ui";
import { useWallet } from "../MiniApp";

export default function ClaimCheck() {
  const { code } = useParams();
  const { refresh } = useWallet();
  const [c, setC] = useState<any>(null);
  const [err, setErr] = useState("");
  const [password, setPassword] = useState("");
  const [answer, setAnswer] = useState("");
  const [done, setDone] = useState<any>(null);
  const load = () => userApi.get(`/checks/view/${code}`).then((r) => setC(r.data)).catch((e) => setErr(errMsg(e)));
  useEffect(() => { load(); }, [code]); // eslint-disable-line react-hooks/exhaustive-deps

  const claim = async () => {
    try {
      const r = await userApi.post(`/checks/claim/${code}`, { password, captcha_token: c.captcha_challenge?.token, captcha_answer: answer });
      setDone(r.data);
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred("success");
      refresh();
    } catch (e) {
      toast.error(errMsg(e));
      setAnswer("");
      load();
    }
  };
  return (
    <div>
      <PageHeader title="Чек" />
      {err && <p className="text-[#FF3366]" data-testid="claim-error">{err}</p>}
      {c && !done && (
        <div className="rise space-y-6">
          <Ticket size={48} className="text-[#00FF66]" weight="duotone" />
          <div className="font-display text-5xl font-black tracking-tighter tabular" data-testid="claim-amount">{c.amount}</div>
          <p className="text-zinc-400">{ASSET_TITLE[c.asset]} {c.description && `· ${c.description}`}</p>
          <div className="flex gap-2"><Status s={c.status} />{c.kind === "multi" && <span className="text-xs text-zinc-500">осталось {c.remaining}/{c.activations}</span>}</div>
          {c.channels?.length > 0 && <p className="text-sm text-zinc-400">Условие: подписка на {c.channels.join(", ")}</p>}
          {c.min_account_age_days > 0 && <p className="text-sm text-zinc-400">Аккаунт не моложе {c.min_account_age_days} дн.</p>}
          {c.has_password && (
            <Field label="Пароль"><input data-testid="claim-password-input" className={inputCls} value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          )}
          {c.captcha_challenge && (
            <Field label={`Капча: ${c.captcha_challenge.question}`}>
              <input data-testid="claim-captcha-input" inputMode="numeric" className={inputCls} value={answer} onChange={(e) => setAnswer(e.target.value)} />
            </Field>
          )}
          {c.already_claimed ? <p className="text-sm text-zinc-400" data-testid="claim-already">Вы уже активировали этот чек</p> :
            <PrimaryButton testid="claim-submit-button" disabled={c.status !== "active"} onClick={claim}>Забрать</PrimaryButton>}
        </div>
      )}
      {done && (
        <div className="rise space-y-4" data-testid="claim-success">
          <p className="text-xs uppercase tracking-[0.25em] text-[#00FF66]">Зачислено</p>
          <div className="font-display text-5xl font-black tracking-tighter tabular">+{done.amount}</div>
          <p className="text-zinc-400">{ASSET_TITLE[done.asset]}</p>
        </div>
      )}
    </div>
  );
}
