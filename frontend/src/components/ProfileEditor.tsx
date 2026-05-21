import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Criteria, Profile } from "@/types/api";
import { CVUploader } from "@/components/CVUploader";
import { CriteriaForm } from "@/components/CriteriaForm";

type Form = {
  name: string;
  full_name: string;
  headline: string;
  current_location: string;
  years_experience: string;
  about_text: string;
};

export function ProfileEditor({ profileId }: { profileId: string }) {
  const qc = useQueryClient();

  const { data: profile } = useQuery({
    queryKey: ["profile", profileId],
    queryFn: async () => (await api.get<Profile>(`/profiles/${profileId}`)).data,
  });

  const { data: criteria } = useQuery({
    queryKey: ["profile-criteria", profileId],
    queryFn: async () =>
      (await api.get<Criteria[]>(`/profiles/${profileId}/criteria`)).data,
  });

  const [form, setForm] = useState<Partial<Form>>({});
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // Reset local form when switching between profiles.
  useEffect(() => {
    setForm({});
  }, [profileId]);

  const save = useMutation({
    mutationFn: () =>
      api.put(`/profiles/${profileId}`, {
        ...form,
        years_experience: form.years_experience
          ? Number(form.years_experience)
          : undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile", profileId] });
      qc.invalidateQueries({ queryKey: ["profiles"] });
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt(null), 2500);
    },
  });

  if (!profile) return <p className="text-sm text-mutedForeground">Cargando perfil…</p>;

  return (
    <div className="space-y-6">
      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-3 font-medium">Datos del perfil</h2>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="text-sm">
            Nombre del perfil
            <input
              defaultValue={profile.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
            />
          </label>
          <label className="text-sm">
            Nombre completo
            <input
              defaultValue={profile.full_name ?? ""}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
            />
          </label>
          <label className="text-sm">
            Headline
            <input
              defaultValue={profile.headline ?? ""}
              onChange={(e) => setForm({ ...form, headline: e.target.value })}
              className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
            />
          </label>
          <label className="text-sm">
            Ubicación
            <input
              defaultValue={profile.current_location ?? ""}
              onChange={(e) =>
                setForm({ ...form, current_location: e.target.value })
              }
              className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
            />
          </label>
          <label className="text-sm">
            Años de experiencia
            <input
              type="number"
              defaultValue={profile.years_experience ?? ""}
              onChange={(e) =>
                setForm({ ...form, years_experience: e.target.value })
              }
              className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
            />
          </label>
          <label className="text-sm md:col-span-2">
            Sobre mí
            <textarea
              defaultValue={profile.about_text ?? ""}
              onChange={(e) => setForm({ ...form, about_text: e.target.value })}
              className="mt-1 block min-h-24 w-full rounded-md border px-3 py-2 text-sm"
            />
          </label>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={() => save.mutate()}
            disabled={save.isPending || Object.keys(form).length === 0}
            className="rounded-md bg-primary px-3 py-2 text-sm text-primaryForeground hover:opacity-90 disabled:opacity-50"
          >
            {save.isPending ? "Guardando…" : "Guardar"}
          </button>
          {savedAt && <span className="text-sm text-success">✓ Guardado</span>}
        </div>
      </section>

      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-3 font-medium">CV base de este perfil</h2>
        <CVUploader
          profileId={profileId}
          initialJson={profile.cv_base_json ?? null}
          hasPdf={Boolean(profile.cv_base_pdf_path)}
        />
      </section>

      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-3 font-medium">Búsquedas de este perfil</h2>
        <CriteriaForm mode="create" profileId={profileId} />

        <p className="mb-2 mt-4 text-sm font-medium">Existentes</p>
        {!criteria || criteria.length === 0 ? (
          <p className="text-sm text-mutedForeground">
            Todavía no creaste búsquedas para este perfil.
          </p>
        ) : (
          <ul className="space-y-2 text-sm">
            {criteria.map((c) => (
              <CriteriaRow key={c.id} c={c} profileId={profileId} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function CriteriaRow({ c, profileId }: { c: Criteria; profileId: string }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);

  const del = useMutation({
    mutationFn: () => api.delete(`/criteria/${c.id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profile-criteria", profileId] }),
  });
  const run = useMutation({
    mutationFn: () => api.post(`/criteria/${c.id}/run`),
  });

  if (editing) {
    return (
      <li>
        <CriteriaForm
          mode="edit"
          profileId={profileId}
          initial={c}
          onDone={() => setEditing(false)}
        />
      </li>
    );
  }

  return (
    <li className="rounded border p-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-medium">
            {c.name ?? "(sin nombre)"}
            {!c.active && (
              <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase text-mutedForeground">
                inactiva
              </span>
            )}
          </p>
          <p className="text-xs text-mutedForeground">
            Keywords: {c.keywords.join(", ") || "—"} · Ubicaciones:{" "}
            {c.locations.join(", ") || "—"} · Modalidades:{" "}
            {c.modalities.join(", ") || "—"}
          </p>
          <p className="text-xs text-mutedForeground">
            Cap diario: {c.daily_apply_cap} · Portales: {c.portals_enabled.join(", ")}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending}
            className="rounded-md border px-2 py-1 text-xs hover:bg-muted disabled:opacity-50"
          >
            {run.isPending ? "Encolando…" : run.isSuccess ? "✓ Encolado" : "Correr ahora"}
          </button>
          <button
            onClick={() => setEditing(true)}
            className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
          >
            Editar
          </button>
          <button
            onClick={() => {
              if (confirm(`Borrar "${c.name ?? "esta búsqueda"}"?`)) del.mutate();
            }}
            disabled={del.isPending}
            className="rounded-md border border-danger px-2 py-1 text-xs text-danger hover:bg-danger/5 disabled:opacity-50"
          >
            Borrar
          </button>
        </div>
      </div>
    </li>
  );
}
