import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";

type Bucket = {
  cost_usd: number;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
};

type ModelRow = { model: string; cost_usd: number; calls: number };
type PurposeRow = { purpose: string; cost_usd: number; calls: number };

type CostSummary = {
  today: Bucket;
  last_7_days: Bucket;
  last_30_days: Bucket;
  all_time: Bucket;
  by_model: ModelRow[];
  by_purpose: PurposeRow[];
};

const PURPOSE_LABEL: Record<string, string> = {
  scoring: "Scoring (Haiku)",
  cv_generation: "CV adaptado",
  letter_generation: "Carta",
  cv_parse: "Parseo de CV",
  other: "Otros",
};

function usd(n: number) {
  if (n < 0.005) return "$0.00";
  if (n < 1) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(2)}`;
}

function shortModel(m: string) {
  return m
    .replace("claude-", "")
    .replace("-20251001", "")
    .replace("-2025", "");
}

export function CostsWidget() {
  const [open, setOpen] = useState(false);
  const { data, isLoading, error } = useQuery({
    queryKey: ["costs", "summary"],
    queryFn: async () => (await api.get<CostSummary>("/costs/summary")).data,
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return (
      <div className="rounded-lg border bg-white p-3 text-xs text-mutedForeground">
        Cargando costos…
      </div>
    );
  }
  if (error || !data) return null;

  const t = data.today;
  const m = data.last_30_days;

  return (
    <div className="rounded-lg border bg-white">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-4 px-3 py-2 text-left hover:bg-muted/40"
      >
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span className="text-xs uppercase text-mutedForeground">Anthropic</span>
          <span>
            <span className="text-mutedForeground">hoy</span>{" "}
            <strong>{usd(t.cost_usd)}</strong>{" "}
            <span className="text-xs text-mutedForeground">({t.calls} calls)</span>
          </span>
          <span>
            <span className="text-mutedForeground">30d</span>{" "}
            <strong>{usd(m.cost_usd)}</strong>{" "}
            <span className="text-xs text-mutedForeground">({m.calls} calls)</span>
          </span>
          <span>
            <span className="text-mutedForeground">total</span>{" "}
            <strong>{usd(data.all_time.cost_usd)}</strong>
          </span>
        </div>
        <span className="text-xs text-mutedForeground">{open ? "▴" : "▾"}</span>
      </button>

      {open && (
        <div className="grid gap-4 border-t px-3 py-3 text-sm md:grid-cols-2">
          <div>
            <p className="mb-1 text-xs font-medium uppercase text-mutedForeground">
              Por modelo (total)
            </p>
            {data.by_model.length === 0 ? (
              <p className="text-xs text-mutedForeground">Sin datos.</p>
            ) : (
              <ul className="space-y-1">
                {data.by_model
                  .slice()
                  .sort((a, b) => b.cost_usd - a.cost_usd)
                  .map((r) => (
                    <li key={r.model} className="flex justify-between gap-2">
                      <span className="font-mono text-xs">{shortModel(r.model)}</span>
                      <span>
                        {usd(r.cost_usd)}{" "}
                        <span className="text-xs text-mutedForeground">({r.calls})</span>
                      </span>
                    </li>
                  ))}
              </ul>
            )}
          </div>
          <div>
            <p className="mb-1 text-xs font-medium uppercase text-mutedForeground">
              Por uso (total)
            </p>
            {data.by_purpose.length === 0 ? (
              <p className="text-xs text-mutedForeground">Sin datos.</p>
            ) : (
              <ul className="space-y-1">
                {data.by_purpose
                  .slice()
                  .sort((a, b) => b.cost_usd - a.cost_usd)
                  .map((r) => (
                    <li key={r.purpose} className="flex justify-between gap-2">
                      <span>{PURPOSE_LABEL[r.purpose] ?? r.purpose}</span>
                      <span>
                        {usd(r.cost_usd)}{" "}
                        <span className="text-xs text-mutedForeground">({r.calls})</span>
                      </span>
                    </li>
                  ))}
              </ul>
            )}
          </div>
          <div className="md:col-span-2 text-xs text-mutedForeground">
            7 días: {usd(data.last_7_days.cost_usd)} · 30 días: {usd(data.last_30_days.cost_usd)} ·
            cache reads hoy: {t.cache_read_tokens.toLocaleString("es-AR")} tokens
          </div>
        </div>
      )}
    </div>
  );
}
