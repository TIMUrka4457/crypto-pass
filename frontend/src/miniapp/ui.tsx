import { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { CaretLeft } from "@phosphor-icons/react";
import { ASSET_LIST, ASSET_TITLE, STATUS_RU } from "@/lib/api";

export function PageHeader({ title, back = true }: { title: string; back?: boolean }) {
  const nav = useNavigate();
  return (
    <div className="sticky top-0 z-20 -mx-4 mb-6 flex items-center gap-3 border-b border-white/10 bg-black/60 px-4 py-4 backdrop-blur-xl sm:-mx-6 sm:px-6">
      {back && (
        <button data-testid="page-back-button" onClick={() => nav("/app")} className="press rounded-full border border-white/10 p-2 hover:border-white/30">
          <CaretLeft size={18} />
        </button>
      )}
      <h1 className="font-display text-lg font-semibold tracking-tight">{title}</h1>
    </div>
  );
}

export function AssetPicker({ value, onChange, assets = ASSET_LIST as readonly string[], testid = "asset-picker" }:
  { value: string; onChange: (a: string) => void; assets?: readonly string[]; testid?: string }) {
  return (
    <div className="grid grid-cols-3 gap-2" data-testid={testid}>
      {assets.map((a) => (
        <button key={a} type="button" data-testid={`${testid}-${a}`} onClick={() => onChange(a)}
          className={`press btn-chip px-2 ${value === a ? "border-[#00FF66] bg-[#00FF66] text-black" : "border-white/15 text-zinc-300 hover:border-white/40"}`}>
          {ASSET_TITLE[a]}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block space-y-2">
      <span className="text-xs uppercase tracking-[0.18em] text-zinc-500">{label}</span>
      {children}
      {hint && <span className="block text-xs text-zinc-500">{hint}</span>}
    </label>
  );
}

const TONE: Record<string, string> = {
  completed: "text-[#00FF66] border-[#00FF66]/40", credited: "text-[#00FF66] border-[#00FF66]/40", paid: "text-[#00FF66] border-[#00FF66]/40",
  active: "text-[#00E5FF] border-[#00E5FF]/40", approved: "text-[#00FF66] border-[#00FF66]/40", delivered: "text-[#00FF66] border-[#00FF66]/40",
  rejected: "text-[#FF3366] border-[#FF3366]/40", failed: "text-[#FF3366] border-[#FF3366]/40", aml_hold: "text-[#FF3366] border-[#FF3366]/40",
  unknown: "text-amber-300 border-amber-300/40", pending_approval: "text-amber-300 border-amber-300/40",
};

export function Status({ s, testid }: { s: string; testid?: string }) {
  return (
    <span data-testid={testid} className={`inline-flex rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${TONE[s] || "text-zinc-300 border-white/15"}`}>
      {STATUS_RU[s] || s}
    </span>
  );
}

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-2xl border border-white/10 bg-[#141414] p-5 ${className}`}>{children}</div>;
}

export function PrimaryButton({ children, testid, disabled, onClick, type = "button" }:
  { children: ReactNode; testid: string; disabled?: boolean; onClick?: () => void; type?: "button" | "submit" }) {
  return (
    <button type={type} data-testid={testid} disabled={disabled} onClick={onClick}
      className="press flex h-14 w-full items-center justify-center rounded-full bg-[#00FF66] px-6 font-display text-sm font-semibold text-black hover:bg-[#33ff85] disabled:opacity-40">
      {children}
    </button>
  );
}

export function Segmented({ options, value, onChange, testid }:
  { options: string[][]; value: string; onChange: (v: string) => void; testid: string }) {
  return (
    <div className="grid grid-cols-2 gap-2" data-testid={testid}>
      {options.map(([k, l]) => (
        <button key={k} type="button" data-testid={`${testid}-${k}`} onClick={() => onChange(k)}
          className={`press btn-chip ${value === k ? "border-[#00E5FF] text-[#00E5FF]" : "border-white/15 text-zinc-400"}`}>{l}</button>
      ))}
    </div>
  );
}

export const inputCls = "h-12 w-full rounded-xl border border-white/10 bg-[#0f0f0f] px-4 text-base text-white placeholder:text-zinc-600 focus:border-[#00FF66] focus:outline-none";
