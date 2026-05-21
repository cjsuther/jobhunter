import { Link } from "react-router-dom";
import type { Match } from "@/types/api";
import { cn } from "@/lib/utils";

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 80
      ? "bg-success text-white"
      : score >= 60
      ? "bg-warning text-white"
      : "bg-mutedForeground text-white";
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", color)}>{score}</span>
  );
}

export function MatchCard({ match }: { match: Match }) {
  return (
    <Link
      to={`/matches/${match.id}`}
      className="block rounded-lg border bg-white p-4 shadow-sm transition hover:shadow"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-medium leading-tight">{match.job.title}</h3>
          <p className="text-sm text-mutedForeground">
            {match.job.company ?? "—"} · {match.job.location ?? "—"} · {match.job.modality ?? "—"}
          </p>
        </div>
        <ScoreBadge score={match.fit_score} />
      </div>
      {match.strengths && match.strengths.length > 0 && (
        <ul className="mt-3 list-disc pl-5 text-sm text-mutedForeground">
          {match.strengths.slice(0, 3).map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-mutedForeground">
        <div className="flex flex-wrap gap-1">
          <span className="rounded bg-muted px-1.5 py-0.5">{match.job.source_portal}</span>
          <span
            className="rounded border border-primary/30 bg-primary/5 px-1.5 py-0.5 text-primary"
            title="Perfil con el que se scoreó este match"
          >
            {match.profile_name}
          </span>
        </div>
        <span>{new Date(match.scored_at).toLocaleString("es-AR")}</span>
      </div>
    </Link>
  );
}
