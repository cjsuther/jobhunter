import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";

type Status = {
  configured: boolean;
  source: "db" | "env" | "none";
  masked_key: string | null;
  last_validated_at: string | null;
  last_validated_ok: boolean | null;
};

type TestResult = { ok: boolean; detail: string | null };

const SOURCE_LABEL: Record<Status["source"], string> = {
  db: "configurada por vos",
  env: "fallback del servidor (.env)",
  none: "no configurada",
};

export function AnthropicKeyPanel() {
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);

  const { data: status } = useQuery({
    queryKey: ["account", "anthropic-key"],
    queryFn: async () => (await api.get<Status>("/account/anthropic-key")).data,
  });

  const save = useMutation({
    mutationFn: (key: string) =>
      api.put<Status>("/account/anthropic-key", { api_key: key }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["account", "anthropic-key"] });
      setDraft("");
      setEditing(false);
    },
  });

  const remove = useMutation({
    mutationFn: () => api.delete("/account/anthropic-key"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["account", "anthropic-key"] }),
  });

  const test = useMutation({
    mutationFn: async () =>
      (await api.post<TestResult>("/account/anthropic-key/test")).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["account", "anthropic-key"] }),
  });

  if (!status) {
    return <p className="text-sm text-mutedForeground">Cargando estado…</p>;
  }

  return (
    <div className="space-y-3">
      <div className="rounded-md border bg-muted/30 p-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase text-mutedForeground">Estado:</span>
          {status.configured ? (
            <span className="rounded-full bg-success/15 px-2 py-0.5 text-xs text-success">
              ● Configurada
            </span>
          ) : (
            <span className="rounded-full bg-danger/15 px-2 py-0.5 text-xs text-danger">
              ○ Sin configurar
            </span>
          )}
          <span className="text-xs text-mutedForeground">
            ({SOURCE_LABEL[status.source]})
          </span>
        </div>
        {status.masked_key && (
          <p className="mt-1 font-mono text-xs">{status.masked_key}</p>
        )}
        {status.last_validated_at && (
          <p className="mt-1 text-xs text-mutedForeground">
            Última prueba: {new Date(status.last_validated_at).toLocaleString("es-AR")} —{" "}
            {status.last_validated_ok ? (
              <span className="text-success">válida</span>
            ) : (
              <span className="text-danger">inválida</span>
            )}
          </p>
        )}
      </div>

      {!editing ? (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => {
              setDraft("");
              setEditing(true);
            }}
            className="rounded-md bg-primary px-3 py-2 text-sm text-primaryForeground hover:opacity-90"
          >
            {status.source === "db" ? "Cambiar key" : "Configurar key"}
          </button>
          {status.configured && (
            <button
              onClick={() => test.mutate()}
              disabled={test.isPending}
              className="rounded-md border px-3 py-2 text-sm hover:bg-muted disabled:opacity-50"
            >
              {test.isPending ? "Probando…" : "Probar key actual"}
            </button>
          )}
          {status.source === "db" && (
            <button
              onClick={() => {
                if (confirm("Borrar tu key de la base de datos? El sistema usará la del .env si está.")) {
                  remove.mutate();
                }
              }}
              disabled={remove.isPending}
              className="rounded-md border border-danger px-3 py-2 text-sm text-danger hover:bg-danger/5 disabled:opacity-50"
            >
              Borrar key
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <input
            type="password"
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="sk-ant-..."
            className="block w-full rounded-md border px-3 py-2 font-mono text-sm"
          />
          <p className="text-xs text-mutedForeground">
            La key se guarda encriptada con Fernet usando MASTER_ENCRYPTION_KEY. No
            queda en logs ni se devuelve en la API después de guardada — solo ves la
            versión enmascarada.
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => save.mutate(draft)}
              disabled={
                save.isPending || !draft.trim() || !draft.startsWith("sk-ant-")
              }
              className="rounded-md bg-primary px-3 py-2 text-sm text-primaryForeground hover:opacity-90 disabled:opacity-50"
            >
              {save.isPending ? "Guardando…" : "Guardar"}
            </button>
            <button
              onClick={() => {
                setDraft("");
                setEditing(false);
              }}
              disabled={save.isPending}
              className="rounded-md border px-3 py-2 text-sm hover:bg-muted"
            >
              Cancelar
            </button>
          </div>
          {save.isError && (
            <p className="text-xs text-danger">
              {(save.error as any)?.response?.data?.detail ?? "Error al guardar"}
            </p>
          )}
        </div>
      )}

      {test.data && (
        <div
          className={
            "rounded-md border p-2 text-sm " +
            (test.data.ok
              ? "border-success/30 bg-success/5 text-success"
              : "border-danger/30 bg-danger/5 text-danger")
          }
        >
          {test.data.ok ? "✓ Key válida" : `✗ ${test.data.detail ?? "Falló la prueba"}`}
        </div>
      )}
    </div>
  );
}
