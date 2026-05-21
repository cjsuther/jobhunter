import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Criteria } from "@/types/api";

const ALL_PORTALS = [
  { value: "bumeran", label: "Bumeran" },
  { value: "zonajobs", label: "ZonaJobs" },
  { value: "computrabajo", label: "Computrabajo" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "clarin", label: "Clarín" },
  { value: "portal_empleo_ba", label: "Portal Empleo BA" },
];

const MODALITIES = [
  { value: "presencial", label: "Presencial" },
  { value: "hibrido", label: "Híbrido" },
  { value: "remoto", label: "Remoto" },
];

type FormState = {
  name: string;
  keywords: string;
  locations: string;
  modalities: string[];
  portals_enabled: string[];
  daily_apply_cap: number;
  salary_min_ars: string;
  active: boolean;
};

const emptyForm: FormState = {
  name: "",
  keywords: "",
  locations: "",
  modalities: [],
  portals_enabled: [],
  daily_apply_cap: 10,
  salary_min_ars: "",
  active: true,
};

function fromCriteria(c: Criteria): FormState {
  return {
    name: c.name ?? "",
    keywords: c.keywords.join(", "),
    locations: c.locations.join(", "),
    modalities: c.modalities,
    portals_enabled: c.portals_enabled,
    daily_apply_cap: c.daily_apply_cap,
    salary_min_ars: c.salary_min_ars != null ? String(c.salary_min_ars) : "",
    active: c.active,
  };
}

function toArray(s: string): string[] {
  return s.split(",").map((x) => x.trim()).filter(Boolean);
}

function toPayload(f: FormState) {
  return {
    name: f.name || null,
    keywords: toArray(f.keywords),
    locations: toArray(f.locations),
    modalities: f.modalities,
    portals_enabled: f.portals_enabled,
    daily_apply_cap: f.daily_apply_cap,
    salary_min_ars: f.salary_min_ars ? Number(f.salary_min_ars) : null,
    seniority_levels: [],
    contract_types: [],
    active: f.active,
  };
}

type Props =
  | { mode: "create"; profileId: string; onDone?: () => void; initial?: undefined }
  | { mode: "edit"; profileId: string; initial: Criteria; onDone?: () => void };

export function CriteriaForm(props: Props) {
  const { mode, profileId, onDone } = props;
  const initial = mode === "edit" ? props.initial : undefined;
  const isEdit = mode === "edit";

  const qc = useQueryClient();
  const [f, setF] = useState<FormState>(initial ? fromCriteria(initial) : emptyForm);
  const [error, setError] = useState<string | null>(null);

  const mutate = useMutation({
    mutationFn: () =>
      isEdit
        ? api.put(`/criteria/${initial!.id}`, toPayload(f))
        : api.post(`/profiles/${profileId}/criteria`, toPayload(f)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["criteria"] });
      qc.invalidateQueries({ queryKey: ["profile-criteria", profileId] });
      if (!isEdit) setF(emptyForm);
      setError(null);
      onDone?.();
    },
    onError: (err: any) => {
      const d = err?.response?.data?.detail;
      setError(
        Array.isArray(d)
          ? d.map((x: any) => x?.msg ?? JSON.stringify(x)).join("; ")
          : typeof d === "string"
          ? d
          : isEdit
          ? "No se pudo guardar"
          : "No se pudo crear"
      );
    },
  });

  const togglePortal = (v: string) =>
    setF((s) => ({
      ...s,
      portals_enabled: s.portals_enabled.includes(v)
        ? s.portals_enabled.filter((x) => x !== v)
        : [...s.portals_enabled, v],
    }));

  const toggleModality = (v: string) =>
    setF((s) => ({
      ...s,
      modalities: s.modalities.includes(v)
        ? s.modalities.filter((x) => x !== v)
        : [...s.modalities, v],
    }));

  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <p className="mb-2 text-sm font-medium">
        {isEdit ? "Editar búsqueda" : "Nueva búsqueda"}
      </p>
      <div className="grid gap-2 md:grid-cols-2">
        <input
          placeholder="Nombre (ej: Senior HRBP CABA)"
          value={f.name}
          onChange={(e) => setF({ ...f, name: e.target.value })}
          className="rounded-md border bg-white px-3 py-2 text-sm"
        />
        <input
          placeholder="Keywords (separadas por coma)"
          value={f.keywords}
          onChange={(e) => setF({ ...f, keywords: e.target.value })}
          className="rounded-md border bg-white px-3 py-2 text-sm"
        />
        <input
          placeholder="Ubicaciones (ej: CABA, GBA Norte)"
          value={f.locations}
          onChange={(e) => setF({ ...f, locations: e.target.value })}
          className="rounded-md border bg-white px-3 py-2 text-sm"
        />
        <input
          placeholder="Salario mínimo en ARS"
          type="number"
          value={f.salary_min_ars}
          onChange={(e) => setF({ ...f, salary_min_ars: e.target.value })}
          className="rounded-md border bg-white px-3 py-2 text-sm"
        />
        <label className="flex items-center gap-2 text-sm">
          <span>Cap diario:</span>
          <input
            type="number"
            min={1}
            max={100}
            value={f.daily_apply_cap}
            onChange={(e) => setF({ ...f, daily_apply_cap: Number(e.target.value) })}
            className="w-20 rounded-md border bg-white px-2 py-1"
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={f.active}
            onChange={(e) => setF({ ...f, active: e.target.checked })}
          />
          <span>Activa (corre en el cron cada 6h)</span>
        </label>
      </div>

      <div className="mt-3">
        <p className="mb-1 text-xs font-medium text-mutedForeground">Modalidades</p>
        <div className="flex flex-wrap gap-2">
          {MODALITIES.map((m) => (
            <button
              key={m.value}
              type="button"
              onClick={() => toggleModality(m.value)}
              className={
                "rounded-full border px-3 py-1 text-xs " +
                (f.modalities.includes(m.value)
                  ? "border-primary bg-primary text-primaryForeground"
                  : "bg-white hover:bg-muted")
              }
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-3">
        <p className="mb-1 text-xs font-medium text-mutedForeground">Portales</p>
        <div className="flex flex-wrap gap-2">
          {ALL_PORTALS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => togglePortal(p.value)}
              className={
                "rounded-full border px-3 py-1 text-xs " +
                (f.portals_enabled.includes(p.value)
                  ? "border-primary bg-primary text-primaryForeground"
                  : "bg-white hover:bg-muted")
              }
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={() => mutate.mutate()}
          disabled={mutate.isPending || f.portals_enabled.length === 0}
          title={f.portals_enabled.length === 0 ? "Elegí al menos un portal" : ""}
          className="rounded-md bg-primary px-3 py-2 text-sm text-primaryForeground hover:opacity-90 disabled:opacity-50"
        >
          {mutate.isPending
            ? isEdit
              ? "Guardando…"
              : "Creando…"
            : isEdit
            ? "Guardar cambios"
            : "Crear búsqueda"}
        </button>
        {isEdit && onDone && (
          <button
            onClick={onDone}
            disabled={mutate.isPending}
            className="rounded-md border px-3 py-2 text-sm hover:bg-muted"
          >
            Cancelar
          </button>
        )}
        {error && <span className="text-sm text-danger">{error}</span>}
      </div>
    </div>
  );
}
