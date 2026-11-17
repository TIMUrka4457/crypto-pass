import { useState } from "react";
import { H, Btn, Table, useLoad } from "../kit";
import { ASSET_LIST, ASSET_TITLE } from "@/lib/api";

export default function Finance() {
  const [days, setDays] = useState(30);
  const { data } = useLoad<any>(`/finance?days=${days}`, [days]);
  return (
    <div>
      <H title="Финансы">
        {[7, 30, 90].map((d) => <Btn key={d} testid={`finance-days-${d}`} tone={d === days ? "primary" : "ghost"} onClick={() => setDays(d)}>{d} дней</Btn>)}
      </H>
      {data && (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {[["Доход с комиссий", data.total.income_usd, "finance-income"], ["Расход на сеть (оценка)", data.total.cost_usd, "finance-cost"],
              ["Прибыль", data.total.profit_usd, "finance-profit"]].map(([l, v, id]) => (
              <div key={id} className="border border-white/10 p-5">
                <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">{l}</p>
                <p data-testid={id} className={`mt-2 font-display text-3xl tabular ${id === "finance-profit" && Number(v) < 0 ? "text-[#FF3366]" : ""}`}>${v}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-zinc-500">Курс: TON ${data.prices.TON}, TRX ${data.prices.TRX}. Стоимость одного вывода: {ASSET_LIST.map((a) => `${ASSET_TITLE[a]} ~$${data.unit_cost_usd[a]}`).join(" · ")}. Доход — чистая часть комиссий после доли рефералов.</p>
          <div className="mt-6">
            <Table testid="finance-table" cols={["День", ...ASSET_LIST.map((a) => ASSET_TITLE[a]), "Доход $", "Расход $", "Прибыль $", "Выводов", "Свипов"]}
              rows={data.rows.map((r: any) => [r.day, ...ASSET_LIST.map((a) => r.income[a]), r.income_usd, r.cost_usd,
                <span key="p" className={Number(r.profit_usd) < 0 ? "text-[#FF3366]" : "text-[#00FF66]"}>{r.profit_usd}</span>, r.withdrawals, r.sweeps])} />
          </div>
        </>
      )}
    </div>
  );
}
