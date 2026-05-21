import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import type { ProfileSummary } from "@/types/api";
import { ProfileEditor } from "@/components/ProfileEditor";

export default function SettingsPage() {
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const { data: profiles, isLoading } = useQuery({
    queryKey: ["profiles"],
    queryFn: async () => (await api.get<ProfileSummary[]>("/profiles")).data,
  });

  const create = useMutation({
    mutationFn: () => api.post("/profiles", { name: newName.trim() || "Nuevo perfil" }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["profiles"] });
      setSelectedId((r.data as ProfileSummary).id);
      setCreating(false);
      setNewName("");
    },
  });

  const del = useMutation({
    mutationFn: (id: string) => api.delete(`/profiles/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profiles"] });
      setSelectedId(null);
    },
    onError: (err: any) => {
      alert(err?.response?.data?.detail ?? "No se pudo borrar");
    },
  });

  // Auto-select the first profile if none picked yet.
  if (!selectedId && profiles && profiles.length > 0 && !creating) {
    setSelectedId(profiles[0].id);
  }

  if (isLoading) return <p className="text-sm text-mutedForeground">Cargando perfiles…</p>;

  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
      <aside className="space-y-3">
        <div className="rounded-lg border bg-white p-3">
          <p className="mb-2 text-sm font-medium">Mis perfiles</p>
          {profiles && profiles.length > 0 ? (
            <ul className="space-y-1">
              {profiles.map((p) => (
                <li key={p.id}>
                  <button
                    onClick={() => {
                      setSelectedId(p.id);
                      setCreating(false);
                    }}
                    className={
                      "block w-full rounded px-2 py-1.5 text-left text-sm " +
                      (p.id === selectedId
                        ? "bg-primary text-primaryForeground"
                        : "hover:bg-muted")
                    }
                  >
                    <p className="leading-tight">{p.name}</p>
                    <p
                      className={
                        "text-[10px] " +
                        (p.id === selectedId
                          ? "text-primaryForeground/70"
                          : "text-mutedForeground")
                      }
                    >
                      {p.headline ?? "(sin headline)"} ·{" "}
                      {p.has_cv ? "CV ✓" : "sin CV"}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-mutedForeground">No tenés perfiles.</p>
          )}

          {creating ? (
            <div className="mt-2 space-y-1">
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Nombre (ej: HRBP CABA)"
                className="block w-full rounded-md border px-2 py-1 text-sm"
              />
              <div className="flex gap-1">
                <button
                  onClick={() => create.mutate()}
                  disabled={create.isPending}
                  className="rounded-md bg-primary px-2 py-1 text-xs text-primaryForeground hover:opacity-90 disabled:opacity-50"
                >
                  {create.isPending ? "Creando…" : "Crear"}
                </button>
                <button
                  onClick={() => {
                    setCreating(false);
                    setNewName("");
                  }}
                  className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
                >
                  Cancelar
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setCreating(true)}
              className="mt-2 w-full rounded-md border border-dashed px-2 py-1.5 text-xs text-mutedForeground hover:bg-muted"
            >
              + Nuevo perfil
            </button>
          )}
        </div>

        {selectedId && profiles && profiles.length > 1 && (
          <button
            onClick={() => {
              const p = profiles.find((x) => x.id === selectedId);
              if (confirm(`Borrar perfil "${p?.name}" y todas sus búsquedas/matches?`)) {
                del.mutate(selectedId);
              }
            }}
            className="block w-full rounded-md border border-danger px-2 py-1.5 text-xs text-danger hover:bg-danger/5"
          >
            Borrar perfil seleccionado
          </button>
        )}
      </aside>

      <section>
        {selectedId ? (
          <ProfileEditor profileId={selectedId} />
        ) : (
          <p className="text-sm text-mutedForeground">
            Creá un perfil para empezar.
          </p>
        )}
      </section>
    </div>
  );
}
