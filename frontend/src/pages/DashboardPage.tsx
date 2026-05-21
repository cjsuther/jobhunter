import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Match, ProfileSummary } from "@/types/api";
import { MatchCard } from "@/components/MatchCard";
import { CostsWidget } from "@/components/CostsWidget";
import { useState } from "react";

export default function DashboardPage() {
  const [minScore, setMinScore] = useState(60);
  const [portal, setPortal] = useState<string>("");
  const [profileId, setProfileId] = useState<string>("");

  const { data: profiles } = useQuery({
    queryKey: ["profiles"],
    queryFn: async () => (await api.get<ProfileSummary[]>("/profiles")).data,
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ["matches", { minScore, portal, profileId }],
    queryFn: async () => {
      const r = await api.get<Match[]>("/matches", {
        params: {
          status: "pending",
          min_score: minScore,
          portal: portal || undefined,
          profile_id: profileId || undefined,
          limit: 50,
        },
      });
      return r.data;
    },
  });

  return (
    <div className="space-y-4">
      <CostsWidget />
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">Cola de matches</h1>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-1">
            <span>Perfil:</span>
            <select
              value={profileId}
              onChange={(e) => setProfileId(e.target.value)}
              className="rounded-md border px-2 py-1"
            >
              <option value="">Todos los perfiles</option>
              {profiles?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1">
            <span>Score mín:</span>
            <input
              type="number"
              min={0}
              max={100}
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              className="w-16 rounded-md border px-2 py-1"
            />
          </label>
          <select
            value={portal}
            onChange={(e) => setPortal(e.target.value)}
            className="rounded-md border px-2 py-1"
          >
            <option value="">Todos los portales</option>
            <option value="bumeran">Bumeran</option>
            <option value="zonajobs">ZonaJobs</option>
            <option value="computrabajo">Computrabajo</option>
            <option value="linkedin">LinkedIn</option>
            <option value="clarin">Clarín</option>
            <option value="portal_empleo_ba">Portal Empleo BA</option>
          </select>
        </div>
      </header>

      {isLoading && <p className="text-sm text-mutedForeground">Cargando…</p>}
      {error && <p className="text-sm text-danger">No se pudo cargar la cola</p>}
      {data && data.length === 0 && (
        <div className="rounded-lg border bg-white p-6 text-sm text-mutedForeground">
          No hay matches pendientes con esos filtros.
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {data?.map((m) => (
          <MatchCard key={m.id} match={m} />
        ))}
      </div>
    </div>
  );
}
