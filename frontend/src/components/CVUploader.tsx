import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

type Props = {
  profileId: string;
  initialJson: Record<string, unknown> | null;
  hasPdf: boolean;
};

type DownloadFmt = "pdf" | "docx" | "json";

async function downloadBaseCV(profileId: string, fmt: DownloadFmt) {
  const r = await api.get(`/profiles/${profileId}/cv/download`, {
    params: { fmt },
    responseType: "blob",
  });
  const cd = (r.headers["content-disposition"] as string | undefined) ?? "";
  const m = /filename="?([^"]+)"?/.exec(cd);
  const name = m?.[1] ?? `cv-base.${fmt}`;
  const url = URL.createObjectURL(r.data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function CVUploader({ profileId, initialJson, hasPdf }: Props) {
  const qc = useQueryClient();
  const [json, setJson] = useState<string>(
    initialJson ? JSON.stringify(initialJson, null, 2) : ""
  );
  const [parseError, setParseError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [downloadingFmt, setDownloadingFmt] = useState<DownloadFmt | null>(null);

  const handleDownload = async (fmt: DownloadFmt) => {
    setDownloadingFmt(fmt);
    try {
      await downloadBaseCV(profileId, fmt);
    } catch (e: any) {
      const detail =
        e?.response?.data instanceof Blob
          ? "Falló la descarga (el backend no tiene el archivo)"
          : e?.response?.data?.detail ?? e?.message ?? "Error";
      alert(`No se pudo descargar: ${detail}`);
    } finally {
      setDownloadingFmt(null);
    }
  };

  const hasJson = Boolean(initialJson && Object.keys(initialJson).length > 0);

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api.post(`/profiles/${profileId}/cv`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return r.data as { cv_base_json: Record<string, unknown> };
    },
    onSuccess: (data) => {
      setJson(JSON.stringify(data.cv_base_json, null, 2));
      setParseError(null);
      qc.invalidateQueries({ queryKey: ["profile", profileId] });
      qc.invalidateQueries({ queryKey: ["profiles"] });
    },
    onError: (err: any) => {
      const d = err?.response?.data?.detail;
      setParseError(typeof d === "string" ? d : "No se pudo parsear el CV");
    },
  });

  const save = useMutation({
    mutationFn: async () => {
      const parsed = JSON.parse(json);
      return api.put(`/profiles/${profileId}/cv`, { cv_base_json: parsed });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile", profileId] });
      qc.invalidateQueries({ queryKey: ["profiles"] });
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt(null), 2500);
    },
    onError: (err: any) => {
      if (err instanceof SyntaxError) {
        setParseError("El JSON no es válido");
      } else {
        const d = err?.response?.data?.detail;
        setParseError(typeof d === "string" ? d : "No se pudo guardar");
      }
    },
  });

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".pdf")) {
      setParseError("El archivo debe ser PDF");
      return;
    }
    setParseError(null);
    upload.mutate(f);
  };

  return (
    <div className="space-y-3">
      <div>
        <p className="mb-1 text-sm">
          {hasPdf ? "Reemplazar CV (PDF)" : "Subir CV (PDF)"}
        </p>
        <p className="mb-2 text-xs text-mutedForeground">
          El CV se sube y Sonnet lo parsea a JSON Resume. Después podés editar el
          resultado abajo y guardar.
        </p>
        <input
          type="file"
          accept="application/pdf,.pdf"
          onChange={onFileChange}
          disabled={upload.isPending}
          className="block text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:text-sm file:text-primaryForeground file:hover:opacity-90 disabled:opacity-50"
        />
        {upload.isPending && (
          <p className="mt-2 text-sm text-mutedForeground">
            Parseando el CV con Claude Sonnet… (puede tardar ~20-40s)
          </p>
        )}
      </div>

      {(hasPdf || hasJson) && (
        <div className="rounded-md border bg-muted/30 p-3">
          <p className="mb-2 text-sm font-medium">Descargar CV cargado</p>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => handleDownload("pdf")}
              disabled={!hasPdf || downloadingFmt !== null}
              title={!hasPdf ? "No subiste un PDF todavía" : "PDF original que subiste"}
              className="rounded-md border px-2 py-1 text-sm hover:bg-muted disabled:opacity-50"
            >
              {downloadingFmt === "pdf" ? "…" : "PDF original"}
            </button>
            <button
              onClick={() => handleDownload("docx")}
              disabled={!hasJson || downloadingFmt !== null}
              title={
                !hasJson
                  ? "Guardá el CV en JSON Resume primero"
                  : "Word generado a partir de los datos estructurados"
              }
              className="rounded-md border px-2 py-1 text-sm hover:bg-muted disabled:opacity-50"
            >
              {downloadingFmt === "docx" ? "…" : "Word (.docx)"}
            </button>
            <button
              onClick={() => handleDownload("json")}
              disabled={!hasJson || downloadingFmt !== null}
              title="JSON Resume con los datos estructurados que usa el LLM"
              className="rounded-md border px-2 py-1 text-sm hover:bg-muted disabled:opacity-50"
            >
              {downloadingFmt === "json" ? "…" : "JSON Resume"}
            </button>
          </div>
        </div>
      )}

      {(json || initialJson) && (
        <div>
          <p className="mb-1 text-sm font-medium">CV estructurado (JSON Resume)</p>
          <p className="mb-2 text-xs text-mutedForeground">
            Podés editar manualmente antes de guardar. Si dejás esto vacío, no se usa
            ningún CV.
          </p>
          <textarea
            value={json}
            onChange={(e) => setJson(e.target.value)}
            spellCheck={false}
            className="block min-h-72 w-full rounded-md border bg-white px-3 py-2 font-mono text-xs"
          />
          <div className="mt-2 flex items-center gap-3">
            <button
              onClick={() => save.mutate()}
              disabled={save.isPending || !json.trim()}
              className="rounded-md bg-primary px-3 py-2 text-sm text-primaryForeground hover:opacity-90 disabled:opacity-50"
            >
              {save.isPending ? "Guardando…" : "Guardar CV"}
            </button>
            {savedAt && <span className="text-sm text-success">✓ Guardado</span>}
            {parseError && <span className="text-sm text-danger">{parseError}</span>}
          </div>
        </div>
      )}

      {!json && !initialJson && parseError && (
        <p className="text-sm text-danger">{parseError}</p>
      )}
    </div>
  );
}
