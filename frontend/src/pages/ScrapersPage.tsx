import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type RawJobOut = {
  external_id: string;
  external_url: string;
  title: string;
  company: string | null;
  location: string | null;
  posted_at: string | null;
};

type PreviewResponse = {
  portal: string;
  keywords: string[];
  locations: string[];
  count: number;
  jobs: RawJobOut[];
  elapsed_seconds: number;
  error: string | null;
};

const SLOW_PORTALS = new Set(["bumeran", "zonajobs"]);

type PortalInfo = { portal: string; available: boolean };

export default function ScrapersPage() {
  const { data: portals } = useQuery({
    queryKey: ["scrapers", "portals"],
    queryFn: async () => (await api.get<PortalInfo[]>("/scrapers/portals")).data,
  });

  const [portal, setPortal] = useState<string>("computrabajo");
  const [keywords, setKeywords] = useState<string>("");
  const [locations, setLocations] = useState<string>("");
  const [maxResults, setMaxResults] = useState<number>(10);

  const [elapsed, setElapsed] = useState(0);
  const tickRef = useRef<number | null>(null);

  const preview = useMutation({
    mutationFn: async () => {
      const params = new URLSearchParams();
      keywords
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean)
        .forEach((k) => params.append("keywords", k));
      locations
        .split(",")
        .map((l) => l.trim())
        .filter(Boolean)
        .forEach((l) => params.append("locations", l));
      params.set("max_results", String(maxResults));
      const r = await api.get<PreviewResponse>(
        `/scrapers/${portal}/preview?${params.toString()}`,
        { timeout: 120_000 }
      );
      return r.data;
    },
  });

  useEffect(() => {
    if (preview.isPending) {
      setElapsed(0);
      const start = Date.now();
      tickRef.current = window.setInterval(() => {
        setElapsed((Date.now() - start) / 1000);
      }, 200);
    } else if (tickRef.current) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
    return () => {
      if (tickRef.current) window.clearInterval(tickRef.current);
    };
  }, [preview.isPending]);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-lg font-semibold">Probar scraper</h1>
        <p className="text-sm text-mutedForeground">
          Ejecuta una búsqueda contra el portal en tiempo real, sin persistir ni encolar
          nada. Útil para verificar que los selectores funcionan y que las keywords
          devuelven lo que esperás.
        </p>
      </header>

      <section className="rounded-lg border bg-white p-4">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="text-sm">
            Portal
            <select
              value={portal}
              onChange={(e) => setPortal(e.target.value)}
              className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
            >
              {portals?.map((p) => (
                <option key={p.portal} value={p.portal}>
                  {p.portal}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            Max resultados
            <input
              type="number"
              min={1}
              max={30}
              value={maxResults}
              onChange={(e) => setMaxResults(Number(e.target.value))}
              className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
            />
          </label>
          <label className="text-sm md:col-span-2">
            Keywords (separadas por coma)
            <input
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="ej: hrbp, recursos humanos"
              className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
            />
          </label>
          <label className="text-sm md:col-span-2">
            Ubicaciones (separadas por coma)
            <input
              value={locations}
              onChange={(e) => setLocations(e.target.value)}
              placeholder="ej: CABA, Buenos Aires"
              className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
            />
          </label>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={() => preview.mutate()}
            disabled={preview.isPending}
            className="rounded-md bg-primary px-3 py-2 text-sm text-primaryForeground hover:opacity-90 disabled:opacity-50"
          >
            {preview.isPending ? `Buscando… (${elapsed.toFixed(1)}s)` : "Probar búsqueda"}
          </button>
          {SLOW_PORTALS.has(portal) && (
            <p className="text-xs text-mutedForeground">
              {portal} usa Playwright (Chromium headless). La primera búsqueda puede
              tardar 15–30s. Tail{" "}
              <code className="rounded bg-muted px-1">docker compose logs -f api</code>{" "}
              para ver progreso.
            </p>
          )}
        </div>
      </section>

      {preview.data && (
        <section className="rounded-lg border bg-white p-4">
          <header className="mb-3 flex items-center justify-between">
            <h2 className="font-medium">
              Resultados ({preview.data.count})
            </h2>
            <span className="text-xs text-mutedForeground">
              {preview.data.portal} · {preview.data.keywords.join(", ") || "(sin keywords)"} ·
              tomó {preview.data.elapsed_seconds}s
            </span>
          </header>
          {preview.data.error && (
            <div className="mb-3 rounded border border-danger/30 bg-danger/5 p-2 text-sm text-danger">
              <strong>Error del scraper:</strong> {preview.data.error}
            </div>
          )}
          {preview.data.jobs.length === 0 ? (
            <p className="text-sm text-mutedForeground">
              0 resultados. Esto suele significar que (a) los selectores del scraper
              están desactualizados, (b) el portal está bloqueando requests, o (c) tus
              keywords no matchean nada.
            </p>
          ) : (
            <ul className="divide-y text-sm">
              {preview.data.jobs.map((j) => (
                <li key={j.external_id} className="py-2">
                  <a
                    href={j.external_url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-medium hover:underline"
                  >
                    {j.title}
                  </a>
                  <p className="text-xs text-mutedForeground">
                    {j.company ?? "—"} · {j.location ?? "—"} · ID: {j.external_id}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
