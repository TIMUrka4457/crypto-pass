import { ReactNode, useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { adminApi, errMsg } from "@/lib/api";

export function useLoad<T = any>(url: string, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null);
  const reload = useCallback(() => {
    adminApi.get(url).then((r) => setData(r.data)).catch((e) => toast.error(errMsg(e)));
  }, [url]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { reload(); }, [reload, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, reload };
}

export function H({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <h1 className="font-display text-3xl font-black tracking-tighter sm:text-4xl">{title}</h1>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

export function Btn({ children, onClick, tone = "ghost", testid, disabled }:
  { children: ReactNode; onClick?: () => void; tone?: "ghost" | "primary" | "danger"; testid: string; disabled?: boolean }) {
  const cls = tone === "primary" ? "bg-[#00FF66] text-black hover:bg-[#33ff85]" : tone === "danger"
    ? "border border-[#FF3366]/50 text-[#FF3366] hover:bg-[#FF3366]/10" : "border border-white/15 text-zinc-200 hover:border-white/40";
  return <button data-testid={testid} disabled={disabled} onClick={onClick} className={`press inline-flex h-9 items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-3.5 text-xs font-medium disabled:opacity-40 ${cls}`}>{children}</button>;
}

export function Table({ cols, rows, testid }: { cols: string[]; rows: ReactNode[][]; testid: string }) {
  return (
    <div className="overflow-x-auto border border-white/10" data-testid={testid}>
      <table className="w-full text-left text-sm">
        <thead className="bg-[#101010] text-[11px] uppercase tracking-[0.14em] text-zinc-500">
          <tr>{cols.map((c) => <th key={c} className="whitespace-nowrap px-3 py-2.5 font-medium">{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={cols.length} className="px-3 py-6 text-zinc-600">Нет данных</td></tr>}
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-white/5 hover:bg-white/[0.02]">
              {r.map((c, j) => <td key={j} className="whitespace-nowrap px-3 py-2.5 align-top tabular">{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Action requiring a mandatory comment; every such action is written to the audit log. */
export function CommentAction({ label, title, tone = "ghost", testid, onSubmit, extra }:
  { label: string; title: string; tone?: "ghost" | "primary" | "danger"; testid: string;
    onSubmit: (comment: string) => Promise<any>; extra?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try { await onSubmit(comment); toast.success("Готово"); setOpen(false); setComment(""); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <>
      <Btn tone={tone} testid={testid} onClick={() => setOpen(true)}>{label}</Btn>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="dark border-white/10 bg-[#111] text-white">
          <DialogHeader><DialogTitle className="font-display">{title}</DialogTitle></DialogHeader>
          {extra}
          <textarea data-testid={`${testid}-comment`} value={comment} onChange={(e) => setComment(e.target.value)} rows={3}
            placeholder="Комментарий (обязательно, попадёт в журнал)" className="w-full rounded-md border border-white/10 bg-black p-3 text-sm" />
          <Btn tone="primary" testid={`${testid}-confirm`} disabled={busy || comment.trim().length < 3} onClick={go}>Подтвердить</Btn>
        </DialogContent>
      </Dialog>
    </>
  );
}

export const short = (s?: string, n = 10) => (s && s.length > n * 2 ? `${s.slice(0, n)}…${s.slice(-6)}` : s || "—");
export const dt = (s?: string) => (s ? new Date(s).toLocaleString("ru-RU") : "—");
export const inp = "rounded-md border border-white/10 bg-black px-3 py-2 text-sm text-white focus:border-[#00FF66] focus:outline-none";
