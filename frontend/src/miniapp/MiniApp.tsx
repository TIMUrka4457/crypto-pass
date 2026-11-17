import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Routes, Route, useNavigate } from "react-router-dom";
import { userApi, errMsg } from "@/lib/api";
import Home from "./pages/Home";
import Deposit from "./pages/Deposit";
import Withdraw from "./pages/Withdraw";
import Transfer from "./pages/Transfer";
import Checks from "./pages/Checks";
import ClaimCheck from "./pages/ClaimCheck";
import Invoices from "./pages/Invoices";
import PayInvoice from "./pages/PayInvoice";
import Referral from "./pages/Referral";
import Merchant from "./pages/Merchant";

type Ctx = { me: any; config: any; refresh: () => Promise<void> };
const WalletCtx = createContext<Ctx>({ me: null, config: null, refresh: async () => {} });
export const useWallet = () => useContext(WalletCtx);

function startParam(): string {
  const tg = window.Telegram?.WebApp;
  return tg?.initDataUnsafe?.start_param || new URLSearchParams(window.location.search).get("start") || "";
}

export default function MiniApp() {
  const [state, setState] = useState<"loading" | "outside" | "error" | "ready">("loading");
  const [error, setError] = useState("");
  const [me, setMe] = useState<any>(null);
  const [config, setConfig] = useState<any>(null);
  const nav = useNavigate();

  const refresh = useCallback(async () => {
    const [m, c] = await Promise.all([userApi.get("/me"), userApi.get("/config")]);
    setMe(m.data);
    setConfig(c.data);
  }, []);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    tg?.ready();
    tg?.expand();
    const init = async () => {
      const initData = tg?.initData || sessionStorage.getItem("tg_init_override") || "";
      if (!initData) {
        const c = await userApi.get("/config").catch(() => null);
        setConfig(c?.data);
        setState("outside");
        return;
      }
      try {
        const r = await userApi.post("/auth/telegram", { init_data: initData });
        sessionStorage.setItem("ut", r.data.token);
        await refresh();
        setState("ready");
        const sp = startParam();
        if (sp.startsWith("c_")) nav(`/app/check/${sp.slice(2)}`, { replace: true });
        if (sp.startsWith("i_")) nav(`/app/invoice/${sp.slice(2)}`, { replace: true });
      } catch (e) {
        setError(errMsg(e));
        setState("error");
      }
    };
    init();
  }, [refresh, nav]);

  if (state === "loading") return <div data-testid="miniapp-loading" className="p-8 font-display text-zinc-500">Загрузка…</div>;
  if (state === "outside" || state === "error") return <Outside error={error} bot={config?.bot_username} />;

  return (
    <WalletCtx.Provider value={{ me, config, refresh }}>
      <div className="relative z-10 mx-auto min-h-screen w-full max-w-md px-4 pb-16 sm:max-w-lg sm:px-6" data-testid="miniapp-root">
        <Routes>
          <Route index element={<Home />} />
          <Route path="deposit" element={<Deposit />} />
          <Route path="withdraw" element={<Withdraw />} />
          <Route path="transfer" element={<Transfer />} />
          <Route path="checks" element={<Checks />} />
          <Route path="check/:code" element={<ClaimCheck />} />
          <Route path="invoices" element={<Invoices />} />
          <Route path="invoice/:code" element={<PayInvoice />} />
          <Route path="referral" element={<Referral />} />
          <Route path="merchant" element={<Merchant />} />
        </Routes>
      </div>
    </WalletCtx.Provider>
  );
}

function Outside({ error, bot }: { error: string; bot?: string }) {
  return (
    <div className="relative z-10 mx-auto flex min-h-screen max-w-md flex-col justify-end px-6 pb-16" data-testid="miniapp-outside">
      <p className="text-xs uppercase tracking-[0.25em] text-[#00FF66]">EasyCrypto</p>
      <h1 className="mt-4 font-display text-4xl font-black leading-none tracking-tighter">Кошелёк живёт внутри Telegram</h1>
      <p className="mt-6 text-zinc-400">
        {error || "Откройте приложение из бота — так мы безопасно узнаем, что это вы, без телефона и почты."}
      </p>
      {bot && (
        <a data-testid="open-bot-link" href={`https://t.me/${bot}`} className="press mt-10 rounded-full bg-[#00FF66] px-6 py-4 text-center font-display text-sm font-semibold text-black">
          Открыть @{bot}
        </a>
      )}
    </div>
  );
}
