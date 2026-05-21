import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import type { Material, MatchDetail } from "@/types/api";

async function downloadMaterial(
  matchId: string,
  materialId: string,
  fmt: "pdf" | "docx" | "md"
) {
  const r = await api.get(`/matches/${matchId}/materials/${materialId}/download`, {
    params: { fmt },
    responseType: "blob",
  });
  const cd = (r.headers["content-disposition"] as string | undefined) ?? "";
  const m = /filename="?([^"]+)"?/.exec(cd);
  const name = m?.[1] ?? `material.${fmt}`;
  const url = URL.createObjectURL(r.data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

type Kind = "cv" | "cover_letter";

const LABEL: Record<Kind, string> = {
  cv: "CV adaptado",
  cover_letter: "Carta de presentación",
};

/** Local UI state for an in-flight regeneration. */
type PendingGen = {
  startedAt: number;
  baseVersion: number; // material version at click time (0 if none existed)
};

function latestMaterial(materials: Material[], type: Kind): Material | undefined {
  return materials
    .filter((m) => m.type === type)
    .sort((a, b) => b.version - a.version)[0];
}

export default function MatchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const qc = useQueryClient();

  const [pending, setPending] = useState<Partial<Record<Kind, PendingGen>>>({});
  const [tick, setTick] = useState(0); // re-render for elapsed timer

  // Re-tick once a second whenever something is pending, just to update the timer.
  useEffect(() => {
    if (Object.keys(pending).length === 0) return;
    const i = window.setInterval(() => setTick((x) => x + 1), 500);
    return () => window.clearInterval(i);
  }, [pending]);

  const isAnyPending = Object.keys(pending).length > 0;

  const { data, isLoading } = useQuery({
    queryKey: ["match", id],
    queryFn: async () => (await api.get<MatchDetail>(`/matches/${id}`)).data,
    enabled: !!id,
    // Poll while a regeneration is in-flight so the new material shows up.
    refetchInterval: isAnyPending ? 3000 : false,
  });

  // Detect when a new version has landed and clear the pending state.
  const seenRef = useRef<Partial<Record<Kind, PendingGen>>>({});
  seenRef.current = pending;
  useEffect(() => {
    if (!data) return;
    const current = seenRef.current;
    const next: Partial<Record<Kind, PendingGen>> = { ...current };
    let changed = false;
    (["cv", "cover_letter"] as Kind[]).forEach((kind) => {
      const p = current[kind];
      if (!p) return;
      const m = latestMaterial(data.materials, kind);
      if (m && m.version > p.baseVersion) {
        delete next[kind];
        changed = true;
      }
      // Hard timeout: 3 minutes — assume failure if nothing arrived.
      if (Date.now() - p.startedAt > 180_000) {
        delete next[kind];
        changed = true;
      }
    });
    if (changed) setPending(next);
  }, [data]);

  const startRegen = (kind: Kind) => {
    const base = latestMaterial(data?.materials ?? [], kind);
    setPending((p) => ({
      ...p,
      [kind]: { startedAt: Date.now(), baseVersion: base?.version ?? 0 },
    }));
    const url =
      kind === "cv" ? `/matches/${id}/regenerate-cv` : `/matches/${id}/regenerate-letter`;
    api.post(url).catch((err) => {
      // If the enqueue itself failed, drop the pending state immediately.
      setPending((p) => {
        const { [kind]: _omit, ...rest } = p;
        return rest;
      });
      alert(`No se pudo encolar: ${err?.response?.data?.detail ?? err.message}`);
    });
  };

  const apply = useMutation({
    mutationFn: () => api.post(`/matches/${id}/apply`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["match", id] });
      if (data?.job.external_url) window.open(data.job.external_url, "_blank");
    },
  });
  const reject = useMutation({
    mutationFn: () => api.post(`/matches/${id}/reject`, { reason: "Descartado por el usuario" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["matches"] });
      nav("/dashboard");
    },
  });
  const markApplied = useMutation({
    mutationFn: () => api.post(`/matches/${id}/mark-applied`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["match", id] }),
  });

  if (isLoading || !data) return <p className="text-sm text-mutedForeground">Cargando…</p>;

  const cv = latestMaterial(data.materials, "cv");
  const letter = latestMaterial(data.materials, "cover_letter");

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <section className="rounded-lg border bg-white p-4">
        <header className="mb-3">
          <h1 className="text-lg font-semibold">{data.job.title}</h1>
          <p className="text-sm text-mutedForeground">
            {data.job.company} · {data.job.location} · {data.job.modality} ·{" "}
            <span className="rounded bg-muted px-1.5 py-0.5">{data.job.source_portal}</span>
          </p>
          <p className="mt-1 text-xs text-mutedForeground">
            Score {data.fit_score} · {data.recommended_action}
          </p>
        </header>
        <article className="prose prose-sm max-w-none whitespace-pre-wrap text-sm">
          {data.job.description ?? "(Sin descripción)"}
        </article>
      </section>

      <section className="space-y-4">
        <div className="rounded-lg border bg-white p-4">
          <h2 className="mb-2 font-medium">Análisis</h2>
          <p className="text-sm">{data.scoring_reasoning ?? "—"}</p>
          {data.strengths && data.strengths.length > 0 && (
            <>
              <p className="mt-2 text-xs font-medium text-success">Fortalezas</p>
              <ul className="list-disc pl-5 text-sm">
                {data.strengths.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </>
          )}
          {data.red_flags && data.red_flags.length > 0 && (
            <>
              <p className="mt-2 text-xs font-medium text-danger">Red flags</p>
              <ul className="list-disc pl-5 text-sm">
                {data.red_flags.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </>
          )}
        </div>

        <MaterialPanel
          matchId={id!}
          kind="cv"
          material={cv}
          pending={pending.cv}
          onRegen={() => startRegen("cv")}
        />

        <MaterialPanel
          matchId={id!}
          kind="cover_letter"
          material={letter}
          pending={pending.cover_letter}
          onRegen={() => startRegen("cover_letter")}
        />

        <div className="flex flex-wrap gap-2">
          <button
            className="rounded-md bg-primary px-3 py-2 text-sm text-primaryForeground hover:opacity-90"
            onClick={() => apply.mutate()}
          >
            Postular (abre portal)
          </button>
          <button
            className="rounded-md border px-3 py-2 text-sm hover:bg-muted"
            onClick={() => markApplied.mutate()}
          >
            Ya postulé manualmente
          </button>
          <button
            className="rounded-md border border-danger px-3 py-2 text-sm text-danger hover:bg-danger/5"
            onClick={() => reject.mutate()}
          >
            Descartar
          </button>
        </div>
      </section>
      {/* tick keeps the elapsed timer fresh; reference it so it's not "unused". */}
      <span className="hidden">{tick}</span>
    </div>
  );
}

function MaterialPanel({
  matchId,
  kind,
  material,
  pending,
  onRegen,
}: {
  matchId: string;
  kind: Kind;
  material: Material | undefined;
  pending: PendingGen | undefined;
  onRegen: () => void;
}) {
  const qc = useQueryClient();
  const elapsed = pending ? (Date.now() - pending.startedAt) / 1000 : 0;
  const showJustGenerated =
    !pending && material && Date.now() - new Date(material.generated_at).getTime() < 10_000;

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [downloadingFmt, setDownloadingFmt] = useState<"pdf" | "docx" | null>(null);

  // Reset draft if the material reloads while we're not editing.
  useEffect(() => {
    if (!editing && material) setDraft(material.content_md);
  }, [material?.id, material?.content_md, editing, material]);

  const save = useMutation({
    mutationFn: (newMd: string) =>
      api.put(`/matches/${matchId}/materials/${material!.id}`, {
        content_md: newMd,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["match", matchId] });
      setEditing(false);
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt(null), 2500);
    },
  });

  const onDownload = async (fmt: "pdf" | "docx") => {
    if (!material) return;
    setDownloadingFmt(fmt);
    try {
      await downloadMaterial(matchId, material.id, fmt);
    } catch (e) {
      alert(`No se pudo descargar: ${e instanceof Error ? e.message : "error"}`);
    } finally {
      setDownloadingFmt(null);
    }
  };

  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-medium">{LABEL[kind]}</h2>
        {material && (
          <span className="text-xs text-mutedForeground">
            v{material.version} ·{" "}
            {new Date(material.generated_at).toLocaleString("es-AR", { hour12: false })}
          </span>
        )}
      </div>

      {pending && (
        <div className="mb-2 flex items-center gap-2 rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-sm">
          <svg
            className="h-4 w-4 animate-spin text-warning"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
            <path fill="currentColor" className="opacity-75" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
          <div>
            <p>Generando con Claude Sonnet…</p>
            <p className="text-xs text-mutedForeground">
              {elapsed.toFixed(0)}s — esto suele tardar 20–40s.
              {material && ` La nueva versión va a reemplazar a la v${material.version}.`}
            </p>
          </div>
        </div>
      )}

      {showJustGenerated && (
        <p className="mb-2 text-sm text-success">✓ Nueva versión generada</p>
      )}
      {savedAt && <p className="mb-2 text-sm text-success">✓ Cambios guardados</p>}

      {!material ? (
        pending ? (
          <p className="text-sm text-mutedForeground">Se va a mostrar acá cuando termine.</p>
        ) : (
          <p className="text-sm text-mutedForeground">Aún no generado.</p>
        )
      ) : editing ? (
        <>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck={false}
            className="block min-h-72 w-full rounded-md border bg-white px-3 py-2 font-mono text-xs"
          />
          <p className="mt-1 text-[10px] text-mutedForeground">
            Markdown: usá <code>**negrita**</code>, <code>*itálica*</code>,{" "}
            <code># título</code>, <code>- bullet</code>. Al guardar se re-renderiza el
            PDF.
          </p>
        </>
      ) : (
        <pre className="max-h-72 overflow-auto rounded bg-muted p-2 text-xs whitespace-pre-wrap">
          {material.content_md}
        </pre>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {material && !editing && (
          <button
            className="rounded-md border px-2 py-1 text-sm hover:bg-muted"
            onClick={() => {
              setDraft(material.content_md);
              setEditing(true);
            }}
          >
            Editar
          </button>
        )}
        {material && editing && (
          <>
            <button
              className="rounded-md bg-primary px-2 py-1 text-sm text-primaryForeground hover:opacity-90 disabled:opacity-50"
              onClick={() => save.mutate(draft)}
              disabled={save.isPending || !draft.trim() || draft === material.content_md}
            >
              {save.isPending ? "Guardando…" : "Guardar"}
            </button>
            <button
              className="rounded-md border px-2 py-1 text-sm hover:bg-muted"
              onClick={() => {
                setDraft(material.content_md);
                setEditing(false);
              }}
              disabled={save.isPending}
            >
              Cancelar
            </button>
          </>
        )}

        <button
          className="rounded-md border px-2 py-1 text-sm hover:bg-muted disabled:opacity-50"
          onClick={onRegen}
          disabled={Boolean(pending) || editing}
          title={
            editing
              ? "Guardá o cancelá la edición antes de regenerar"
              : pending
              ? "Esperá a que termine la generación actual"
              : ""
          }
        >
          {pending ? `Generando… (${elapsed.toFixed(0)}s)` : material ? "Regenerar" : "Generar"}
        </button>

        {material && (
          <>
            <button
              className="rounded-md border px-2 py-1 text-sm hover:bg-muted disabled:opacity-50"
              onClick={() => onDownload("docx")}
              disabled={Boolean(downloadingFmt) || editing}
            >
              {downloadingFmt === "docx" ? "…" : "Descargar Word"}
            </button>
            <button
              className="rounded-md border px-2 py-1 text-sm hover:bg-muted disabled:opacity-50"
              onClick={() => onDownload("pdf")}
              disabled={Boolean(downloadingFmt) || editing}
            >
              {downloadingFmt === "pdf" ? "…" : "Descargar PDF"}
            </button>
            <button
              className="rounded-md border px-2 py-1 text-sm hover:bg-muted"
              onClick={() => navigator.clipboard.writeText(material.content_md)}
              disabled={editing}
            >
              Copiar texto
            </button>
          </>
        )}
      </div>

      {save.isError && (
        <p className="mt-2 text-xs text-danger">
          No se pudo guardar:{" "}
          {(save.error as any)?.response?.data?.detail ?? (save.error as Error)?.message}
        </p>
      )}
    </div>
  );
}
