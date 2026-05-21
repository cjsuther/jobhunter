import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Funnel } from "@/types/api";

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border bg-white p-4">
      <p className="text-xs uppercase text-mutedForeground">{label}</p>
      <p className="text-2xl font-semibold">{value}</p>
    </div>
  );
}

export default function TrackingPage() {
  const { data } = useQuery({
    queryKey: ["funnel"],
    queryFn: async () => (await api.get<Funnel>("/tracking/funnel")).data,
  });

  if (!data) return <p className="text-sm text-mutedForeground">Cargando…</p>;

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Tracking</h1>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
        <Stat label="Scoreadas" value={data.scored} />
        <Stat label="≥ threshold" value={data.above_threshold} />
        <Stat label="Aprobadas" value={data.approved} />
        <Stat label="Aplicadas" value={data.applied} />
        <Stat label="Respondieron" value={data.responded} />
        <Stat label="Entrevista" value={data.interview} />
        <Stat label="Ofertas" value={data.offer} />
      </div>
    </div>
  );
}
