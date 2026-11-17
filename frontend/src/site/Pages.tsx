import { useEffect, useState } from "react";
import { userApi, ASSET_TITLE } from "@/lib/api";
import { Site, PageTitle, Card, BotButton, useBot } from "./Site";

const STEPS = [
  ["Нажмите «Старт» в боте", "Кошелёк создаётся сразу. Ваш аккаунт привязан к Telegram — никаких паролей и анкет."],
  ["Пополните баланс", "Бот покажет личный адрес и QR-код в сети TON или TRON. Мемо не нужно — зачисление после подтверждений сети."],
  ["Пользуйтесь прямо в чате", "Баланс, переводы, чеки, обмен и счета — кнопками в одном сообщении. Или откройте мини-приложение."],
  ["Выводите когда угодно", "Укажите адрес и сумму — бот покажет точную комиссию до подтверждения. Обычно вывод занимает пару минут."],
];

export function HowItWorks() {
  const bot = useBot();
  return (
    <Site>
      <PageTitle kicker="Как это работает" title="Четыре шага от старта до первого перевода">
        <p>EasyCrypto — кастодиальный кошелёк: мы храним средства и ведём учёт, поэтому переводы между пользователями мгновенные и бесплатные.</p>
      </PageTitle>
      <div className="mt-14 grid grid-cols-1 gap-4 md:grid-cols-2">{STEPS.map(([t, d], i) => <Card key={t} n={`ШАГ ${i + 1}`} title={t} text={d} />)}</div>
      <section className="mt-20 grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card title="Чеки в любом чате" text={<>В любом диалоге наберите <code className="text-[#00FF66]">@{bot || "бот"} 5 usdt</code> и выберите чек. Деньги спишутся, только когда получатель нажмёт «Забрать».</>} />
        <Card title="Обмен" text="TON ↔ USDT по рыночному курсу. Курс и комиссия показываются до подтверждения, проскальзывание защищено." />
        <Card title="Счета" text="Ссылка на оплату для друзей и клиентов. Оплатить можно с баланса или переводом из любого кошелька." />
      </section>
      <div className="mt-16"><BotButton bot={bot} testid="how-open-bot" label="Начать в Telegram" /></div>
    </Site>
  );
}

export function Fees() {
  const [f, setF] = useState<any>(null);
  useEffect(() => { userApi.get("/fees").then((r) => setF(r.data)).catch(() => {}); }, []);
  const rows: [string, string][] = f ? [
    ["Переводы по @username, чеки, счета", "Бесплатно"],
    ["Обмен TON ↔ USDT", `${f.swap_pct}%`],
    [`Вывод ${ASSET_TITLE.TON}`, `${f.withdraw.TON} TON`],
    [`Вывод ${ASSET_TITLE.USDT_TON}`, `${f.withdraw.USDT_TON} USDT`],
    [`Вывод ${ASSET_TITLE.USDT_TRC20}`, `${f.withdraw.USDT_TRC20} USDT · на новый адрес ${f.withdraw.USDT_TRC20_new} USDT`],
    ["Пополнение TON и USDT TON", "Бесплатно"],
    [`Пополнение ${ASSET_TITLE.USDT_TRC20}`, `${f.deposit.USDT_TRC20} USDT, не больше 10% суммы`],
    ["Приём платежей (мерчанты)", `${f.merchant_pct}%`],
  ] : [];
  return (
    <Site>
      <PageTitle kicker="Комиссии" title="Честные комиссии без сюрпризов">
        <p>Внутри кошелька всё бесплатно. За вывод берём реальную стоимость газа сети по текущему курсу плюс небольшую фиксированную наценку — поэтому сумма может немного меняться. Точная цифра всегда видна до подтверждения.</p>
      </PageTitle>
      <div className="mt-14 border border-white/10" data-testid="fees-table">
        {rows.map(([k, v]) => (
          <div key={k} className="grid gap-1 border-b border-white/5 p-5 sm:grid-cols-[1fr_auto] sm:gap-6">
            <span className="text-sm text-zinc-300">{k}</span><span className="font-mono-num text-sm text-[#00FF66]">{v}</span>
          </div>
        ))}
        {!f && <p className="p-5 text-sm text-zinc-500">Загрузка…</p>}
      </div>
      {f && <p className="mt-4 text-sm text-zinc-500">Почему вывод USDT TRC20 дороже на новый адрес: сеть TRON берёт вдвое больше энергии за первый USDT на адресе. Рефералы получают {f.referral_pct}% от комиссий приглашённых.</p>}
    </Site>
  );
}

const FAQ = [
  ["Нужна ли верификация?", "Нет. Аккаунт создаётся по Telegram ID."],
  ["Сколько идёт пополнение?", "TON — около минуты, TRON — 1–2 минуты после отправки. Бот пришлёт уведомление."],
  ["Почему вывод «на проверке»?", "Крупные выводы проверяет сотрудник — это защищает ваши средства. Обычно это занимает несколько минут."],
  ["Что будет, если отменить чек?", "Неиспользованная сумма сразу вернётся на баланс."],
  ["Я отправил не тот токен", "Зачисляются только TON, оригинальный USDT в сети TON и USDT TRC20. Напишите в поддержку через бота."],
  ["Где хранятся деньги?", "Небольшая часть — в горячем кошельке для быстрых выводов, основная — в холодном хранилище."],
];

export function Faq() {
  const bot = useBot();
  return (
    <Site>
      <PageTitle kicker="Вопросы" title="Частые вопросы" />
      <div className="mt-14 divide-y divide-white/10 border-y border-white/10">
        {FAQ.map(([q, a], i) => (
          <details key={q} data-testid={`faq-item-${i}`} className="group py-5">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-6 font-display text-base">{q}<span className="text-[#00FF66] transition-transform group-open:rotate-45">+</span></summary>
            <p className="mt-3 max-w-2xl text-sm text-zinc-400">{a}</p>
          </details>
        ))}
      </div>
      <div className="mt-14"><BotButton bot={bot} testid="faq-open-bot" label="Задать вопрос в боте" /></div>
    </Site>
  );
}
