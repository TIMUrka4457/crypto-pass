import { useEffect, useState } from "react";
import { ArrowRight } from "@phosphor-icons/react";
import { userApi } from "@/lib/api";

const ENDPOINTS = [
  ["GET", "/api/v1/balance", "Баланс мерчанта по всем активам"],
  ["POST", "/api/v1/invoices", "Создать счёт: asset, amount, description, payload, kind (single|multi), max_payments, expires_in"],
  ["GET", "/api/v1/invoices/{id}", "Статус счёта: active, paid, cancelled, expired"],
  ["POST", "/api/v1/transfers", "Внутренний перевод: to_username | to_tg_id, asset, amount, idempotency_key"],
  ["POST", "/api/v1/payouts", "Выплата на внешний адрес: asset, address, amount, idempotency_key"],
  ["GET", "/api/v1/payouts/{id}", "Статус выплаты и хеш транзакции"],
];

const WEBHOOK = `POST https://ваш-сайт/webhook
X-Signature: hex(HMAC_SHA256(webhook_secret, X-Timestamp + "." + body))
X-Timestamp: 1767225600
X-Event-Id: evt_…

{"event":"invoice.paid","invoice_id":"inv_…","asset":"USDT_TON","amount":"25","payload":"order-1842", …}`;

export default function Landing() {
  const [bot, setBot] = useState<string | null>(null);
  useEffect(() => { userApi.get("/config").then((r) => setBot(r.data.bot_username)).catch(() => {}); }, []);
  const base = process.env.REACT_APP_BACKEND_URL;
  return (
    <div className="relative z-10 mx-auto max-w-6xl px-6 py-14 sm:px-10">
      <header className="flex items-center justify-between">
        <p className="font-display text-lg font-black tracking-tighter">Easy<span className="text-[#00FF66]">Crypto</span></p>
        <a href="#api" data-testid="landing-api-link" className="text-sm text-zinc-500 hover:text-white">API</a>
      </header>
      <section className="mt-24 grid gap-12 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <h1 className="font-display text-4xl font-black leading-[0.95] tracking-tighter sm:text-5xl lg:text-6xl">
            Кошелёк в Telegram.<br /><span className="text-[#00FF66]">Платёжный шлюз</span> для всех остальных.
          </h1>
          <p className="mt-8 max-w-xl text-zinc-400">TON, USDT-TON и USDT TRC20. Переводы по @username бесплатно, чеки и мульти-чеки с условиями, счета, рефералка — и API для магазинов, ботов и игр.</p>
          {bot && (
            <a data-testid="landing-open-bot" href={`https://t.me/${bot}`} className="press mt-10 inline-flex items-center gap-3 rounded-full bg-[#00FF66] px-7 py-4 font-display text-sm font-semibold text-black hover:bg-[#33ff85]">
              Открыть @{bot} <ArrowRight weight="bold" />
            </a>
          )}
        </div>
        <div className="space-y-px self-end border border-white/10">
          {[["01", "Аккаунт по Telegram ID", "без телефона и почты"], ["02", "Свой адрес депозита", "мемо не нужно"], ["03", "Чеки с автовозвратом", "по сроку действия"], ["04", "Вебхуки с HMAC", "и повторами отправки"]].map(([n, t, s]) => (
            <div key={n} className="flex gap-5 bg-[#0c0c0c] p-5"><span className="font-mono-num text-xs text-[#00E5FF]">{n}</span><div><p className="text-sm">{t}</p><p className="text-xs text-zinc-500">{s}</p></div></div>
          ))}
        </div>
      </section>
      <section id="api" className="mt-32">
        <h2 className="font-display text-2xl font-bold tracking-tight">API мерчанта</h2>
        <p className="mt-3 text-zinc-400">Ключ создаётся в кабинете мерчанта в Mini App. Передавайте его в заголовке <code className="text-[#00FF66]">X-API-Key</code>. Базовый адрес: <code className="text-zinc-200">{base}</code></p>
        <div className="mt-8 border border-white/10" data-testid="api-endpoints">
          {ENDPOINTS.map(([m, p, d]) => (
            <div key={p + m} className="grid gap-2 border-b border-white/5 p-4 sm:grid-cols-[70px_260px_1fr]">
              <span className={`font-mono-num text-xs ${m === "GET" ? "text-[#00E5FF]" : "text-[#00FF66]"}`}>{m}</span>
              <span className="font-mono-num text-sm">{p}</span>
              <span className="text-sm text-zinc-400">{d}</span>
            </div>
          ))}
        </div>
        <h3 className="mt-12 font-display text-lg">Вебхуки</h3>
        <pre className="mt-4 overflow-x-auto border border-white/10 bg-[#0c0c0c] p-5 font-mono-num text-xs text-zinc-300">{WEBHOOK}</pre>
        <p className="mt-3 text-sm text-zinc-500">Ответьте 2xx — иначе повторим до 8 раз с растущей паузой. Суммы передаются строками, idempotency_key защищает от двойных списаний.</p>
      </section>
    </div>
  );
}
