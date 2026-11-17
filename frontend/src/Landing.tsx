import { Site, PageTitle, Card, BotButton, useBot } from "@/site/Site";

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

export default function Business() {
  const bot = useBot();
  const base = process.env.REACT_APP_BACKEND_URL;
  return (
    <Site>
      <PageTitle kicker="Для бизнеса" title={<>Принимайте крипту<br /><span className="text-[#00FF66]">в магазине, боте и игре</span></>}>
        <p>Счета с оплатой с баланса EasyCrypto или переводом из любого кошелька, выплаты пользователям и вебхуки с подписью HMAC.</p>
      </PageTitle>
      <div className="mt-14 grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card n="01" title="Подайте заявку" text="В мини-приложении откройте «Мерчант» и заполните название и сайт. Мы одобрим заявку и назначим комиссию." />
        <Card n="02" title="Создайте API-ключ" text="Ключ передаётся в заголовке X-API-Key. До 5 активных ключей, отзыв в один клик." />
        <Card n="03" title="Подключите вебхук" text="Укажите https-адрес — мы сообщим об оплате счёта и повторим отправку до 8 раз." />
      </div>
      <section id="api" className="mt-24">
        <h2 className="font-display text-2xl font-bold tracking-tight">API мерчанта</h2>
        <p className="mt-3 break-all text-zinc-400">Базовый адрес: <code className="text-zinc-200">{base}</code></p>
        <div className="mt-8 border border-white/10" data-testid="api-endpoints">
          {ENDPOINTS.map(([m, p, d]) => (
            <div key={p + m} className="grid gap-2 border-b border-white/5 p-4 sm:grid-cols-[70px_260px_1fr]">
              <span className={`font-mono-num text-xs ${m === "GET" ? "text-[#00E5FF]" : "text-[#00FF66]"}`}>{m}</span>
              <span className="break-all font-mono-num text-sm">{p}</span>
              <span className="text-sm text-zinc-400">{d}</span>
            </div>
          ))}
        </div>
        <h3 className="mt-12 font-display text-lg">Вебхуки</h3>
        <pre className="mt-4 overflow-x-auto border border-white/10 bg-[#0c0c0c] p-5 font-mono-num text-xs text-zinc-300">{WEBHOOK}</pre>
        <p className="mt-3 text-sm text-zinc-500">Ответьте 2xx — иначе повторим до 8 раз с растущей паузой. Суммы передаются строками, idempotency_key защищает от двойных списаний.</p>
      </section>
      <div className="mt-16"><BotButton bot={bot} testid="business-open-bot" label="Стать мерчантом" /></div>
    </Site>
  );
}
