import { Link } from "react-router-dom";
import { Site, PageTitle, Card, BotButton, useBot } from "./Site";

const FEATURES = [
  ["Кошелёк без регистрации", "Аккаунт создаётся по Telegram ID. Ни телефона, ни почты, ни паролей — просто нажмите «Старт» в боте."],
  ["Переводы по @username", "Отправьте TON или USDT любому пользователю бота. Бесплатно и мгновенно — деньги не уходят в блокчейн."],
  ["Чеки", "Ссылка, по которой получатель забирает крипту. Можно прямо в любом чате: наберите @бот 5 usdt."],
  ["Обмен TON ↔ USDT", "По рыночному курсу за пару секунд, без бирж и верификации."],
  ["Счета", "Выставьте счёт и отправьте ссылку — оплатят с баланса или переводом из любого кошелька."],
  ["Рефералы", "Делитесь ссылкой и получайте процент от комиссий друзей навсегда."],
];

export default function Home() {
  const bot = useBot();
  return (
    <Site>
      <PageTitle kicker="TON · USDT TON · USDT TRC20" title={<>Кошелёк в Telegram.<br /><span className="text-[#00FF66]">Платёжный шлюз</span> для всех остальных.</>}>
        <p>Храните, переводите, меняйте и принимайте криптовалюту прямо в чате Telegram — кнопками в боте или в удобном мини-приложении.</p>
        <div className="mt-10 flex flex-wrap gap-3">
          <BotButton bot={bot} testid="landing-open-bot" />
          <Link to="/how-it-works" data-testid="landing-how" className="press btn-secondary h-14 px-7">Как это работает</Link>
        </div>
      </PageTitle>
      <section className="mt-20 grid grid-cols-2 gap-px border border-white/10 bg-white/10 sm:grid-cols-4">
        {[["0", "комиссия за переводы"], ["3", "актива в двух сетях"], ["24/7", "автоматические выводы"], ["1 мин", "до первого перевода"]].map(([v, l]) => (
          <div key={l} className="bg-[#0a0a0a] p-6"><p className="font-display text-3xl font-black text-[#00FF66]">{v}</p><p className="mt-2 text-xs text-zinc-500">{l}</p></div>
        ))}
      </section>
      <section className="mt-24">
        <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">Что умеет кошелёк</h2>
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(([t, d], i) => <Card key={t} n={String(i + 1).padStart(2, "0")} title={t} text={d} />)}
        </div>
      </section>
      <section className="mt-24 grid gap-10 border border-white/10 bg-[#0c0c0c] p-8 sm:p-12 lg:grid-cols-[1.2fr_1fr]">
        <div>
          <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">Безопасность — по умолчанию</h2>
          <p className="mt-4 text-zinc-400">Большая часть средств хранится в холодных кошельках. Каждая операция проходит через двойную бухгалтерию с автоматической сверкой, крупные выводы проверяются вручную, а подозрительная активность сразу останавливается.</p>
        </div>
        <ul className="space-y-3 text-sm text-zinc-300">
          {["Холодное хранение основной части средств", "Ручная проверка крупных выводов", "Лимиты на операции и в сутки", "Блок-лист подозрительных адресов", "Круглосуточный мониторинг аномалий"].map((x) => <li key={x} className="border-b border-white/5 pb-3">{x}</li>)}
        </ul>
      </section>
      <section className="mt-24 flex flex-col items-start gap-6 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="max-w-xl font-display text-2xl font-bold tracking-tight sm:text-3xl">Принимаете оплату? Подключите шлюз за вечер.</h2>
        <Link to="/business" data-testid="landing-business" className="press btn-secondary h-14 px-7">API и вебхуки</Link>
      </section>
    </Site>
  );
}
