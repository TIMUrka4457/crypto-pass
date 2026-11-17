import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const userApi = axios.create({ baseURL: API });
userApi.interceptors.request.use((c) => {
  const t = sessionStorage.getItem("ut");
  if (t) c.headers.Authorization = `Bearer ${t}`;
  return c;
});

export const adminApi = axios.create({ baseURL: `${API}/admin` });
adminApi.interceptors.request.use((c) => {
  const t = localStorage.getItem("at");
  if (t) c.headers.Authorization = `Bearer ${t}`;
  return c;
});
adminApi.interceptors.response.use(
  (r) => r,
  (e) => {
    if (e?.response?.status === 401 && localStorage.getItem("at")) {
      localStorage.removeItem("at");
      window.location.href = "/admin";
    }
    return Promise.reject(e);
  }
);

export function errMsg(e: any): string {
  const d = e?.response?.data?.detail;
  if (Array.isArray(d)) return d.map((x) => x.msg).join("; ");
  return d || e?.message || "Ошибка";
}

export const idem = () =>
  (window.crypto?.randomUUID ? window.crypto.randomUUID() : String(Date.now()) + Math.random()).replace(/[^a-z0-9]/gi, "").slice(0, 32);

export const ASSET_LIST = ["TON", "USDT_TON", "USDT_TRC20"] as const;
export const ASSET_TITLE: Record<string, string> = { TON: "TON", USDT_TON: "USDT · TON", USDT_TRC20: "USDT · TRC20" };
export const ASSET_NET: Record<string, string> = { TON: "ton", USDT_TON: "ton", USDT_TRC20: "tron" };

export const STATUS_RU: Record<string, string> = {
  active: "Активен", done: "Использован", cancelled: "Отменён", expired: "Истёк", paid: "Оплачен",
  confirming: "Подтверждается", checking: "Проверка", credited: "Зачислен", aml_hold: "AML-проверка", rejected: "Отклонён",
  pending_approval: "Ждёт одобрения", queued: "В очереди", signing: "Подпись", broadcasting: "Отправка", sent: "Отправлен",
  unknown: "Статус неизвестен", completed: "Выполнен", failed: "Ошибка", pending: "На рассмотрении", approved: "Одобрен",
  suspended: "Приостановлен", delivered: "Доставлен", running: "Идёт", partially_paid: "Частично",
};
