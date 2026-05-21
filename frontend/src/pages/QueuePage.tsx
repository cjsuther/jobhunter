import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";

type WorkerInfo = {
  name: string;
  status: string;
  active: number;
  reserved: number;
  queues: string[];
};

type QueueDepth = { name: string; pending: number };

type QueueStatus = {
  workers: WorkerInfo[];
  queues: QueueDepth[];
  inspected_at: string;
};

type RecentJob = {
  id: string;
  title: string;
  company: string | null;
  portal: string;
  scraped_at: string;
};

type RecentMatch = {
  id: string;
  job_title: string;
  portal: string;
  fit_score: number;
  status: string;
  scored_at: string;
};

type RecentMaterial = {
  id: string;
  match_id: string;
  type: string;
  version: number;
  generated_at: string;
};

type ActiveTask = {
  task_id: string;
  name: string;
  worker: string;
  args: unknown[];
  elapsed_seconds: number | null;
  eta: string | null;
};

type Activity = {
  jobs_last_24h: number;
  matches_last_24h: number;
  materials_last_24h: number;
  recent_jobs: RecentJob[];
  recent_matches: RecentMatch[];
  recent_materials: RecentMaterial[];
};

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString("es-AR", { hour12: false });
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border bg-white p-3">
      <p className="text-xs uppercase text-mutedForeground">{label}</p>
      <p className="text-2xl font-semibold">{value}</p>
    </div>
  );
}

export default function QueuePage() {
  const qc = useQueryClient();

  const statusQ = useQuery({
    queryKey: ["queue", "status"],
    queryFn: async () => (await api.get<QueueStatus>("/queue/status")).data,
    refetchInterval: 3000,
  });

  const activityQ = useQuery({
    queryKey: ["queue", "activity"],
    queryFn: async () => (await api.get<Activity>("/queue/activity")).data,
    refetchInterval: 5000,
  });

  const activeQ = useQuery({
    queryKey: ["queue", "active"],
    queryFn: async () => (await api.get<ActiveTask[]>("/queue/active")).data,
    refetchInterval: 3000,
  });

  const cancel = useMutation({
    mutationFn: (taskId: string) =>
      api.post(`/queue/tasks/${taskId}/cancel`, null, {
        params: { terminate: true },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["queue", "active"] });
      qc.invalidateQueries({ queryKey: ["queue", "status"] });
    },
  });

  const purge = useMutation({
    mutationFn: (queueName: string) => api.post(`/queue/queues/${queueName}/purge`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["queue", "status"] });
    },
  });

  const status = statusQ.data;
  const activity = activityQ.data;
  const statusAt = statusQ.dataUpdatedAt;
  const initialLoading = statusQ.isPending || activityQ.isPending;
  const refreshing = statusQ.isFetching || activityQ.isFetching;

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["queue", "status"] });
    qc.invalidateQueries({ queryKey: ["queue", "activity"] });
    qc.invalidateQueries({ queryKey: ["queue", "active"] });
  };

  const totalPending = status?.queues.reduce((acc, q) => acc + q.pending, 0) ?? 0;
  const totalActive = status?.workers.reduce((acc, w) => acc + w.active, 0) ?? 0;

  if (initialLoading) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-mutedForeground">
        <svg
          className="h-6 w-6 animate-spin"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
          <path
            fill="currentColor"
            className="opacity-75"
            d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
          />
        </svg>
        <p className="text-sm">Consultando workers y Redis…</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">Cola de procesamiento</h1>
        <div className="flex items-center gap-3 text-xs text-mutedForeground">
          <span>
            Auto-refresca cada 3s
            {statusAt ? ` · última: ${fmtTime(new Date(statusAt).toISOString())}` : ""}
          </span>
          <button
            onClick={refresh}
            disabled={refreshing}
            className="flex items-center gap-1 rounded-md border px-2 py-1 hover:bg-muted disabled:opacity-50"
            title="Refrescar ahora"
          >
            <svg
              className={"h-3.5 w-3.5 " + (refreshing ? "animate-spin" : "")}
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            {refreshing ? "Refrescando…" : "Refrescar"}
          </button>
        </div>
      </header>

      <section>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat label="Pendientes" value={totalPending} />
          <Stat label="Corriendo" value={totalActive} />
          <Stat label="Jobs (24h)" value={activity?.jobs_last_24h ?? 0} />
          <Stat label="Matches (24h)" value={activity?.matches_last_24h ?? 0} />
          <Stat label="Materiales (24h)" value={activity?.materials_last_24h ?? 0} />
        </div>
      </section>

      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-3 font-medium">Workers</h2>
        {!status?.workers.length ? (
          <p className="text-sm text-danger">
            No hay workers online. Verificá que estén corriendo:{" "}
            <code className="rounded bg-muted px-1">docker compose ps</code>
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-mutedForeground">
              <tr>
                <th className="py-2">Worker</th>
                <th>Estado</th>
                <th>Corriendo</th>
                <th>Reservadas</th>
                <th>Colas</th>
              </tr>
            </thead>
            <tbody>
              {status.workers.map((w) => (
                <tr key={w.name} className="border-t">
                  <td className="py-2 font-mono text-xs">{w.name}</td>
                  <td>
                    <span className="rounded-full bg-success/15 px-2 py-0.5 text-xs text-success">
                      {w.status}
                    </span>
                  </td>
                  <td>{w.active}</td>
                  <td>{w.reserved}</td>
                  <td className="text-xs text-mutedForeground">{w.queues.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-3 font-medium">Tareas en ejecución</h2>
        {!activeQ.data?.length ? (
          <p className="text-sm text-mutedForeground">Ninguna tarea corriendo en este momento.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-mutedForeground">
              <tr>
                <th className="py-2">Tarea</th>
                <th>Worker</th>
                <th>Args</th>
                <th>Corriendo</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {activeQ.data.map((t) => {
                const shortName = t.name.replace("app.workers.", "").replace("_tasks.", ".");
                const isStuck = (t.elapsed_seconds ?? 0) > 60;
                return (
                  <tr key={t.task_id} className="border-t">
                    <td className="py-2">
                      <p className="font-mono text-xs">{shortName}</p>
                      <p className="text-[10px] text-mutedForeground">{t.task_id.slice(0, 8)}…</p>
                    </td>
                    <td className="font-mono text-xs">{t.worker.split("@")[1] ?? t.worker}</td>
                    <td className="font-mono text-[11px] text-mutedForeground">
                      {JSON.stringify(t.args).slice(0, 60)}
                    </td>
                    <td className={isStuck ? "text-warning" : ""}>
                      {t.elapsed_seconds !== null ? `${t.elapsed_seconds.toFixed(0)}s` : "—"}
                    </td>
                    <td>
                      <button
                        onClick={() => {
                          if (
                            confirm(
                              `Cancelar ${shortName} (${t.task_id.slice(0, 8)}…)?\n\nVa a terminar el proceso del worker — la tarea no podrá retomar.`
                            )
                          ) {
                            cancel.mutate(t.task_id);
                          }
                        }}
                        disabled={cancel.isPending}
                        className="rounded-md border border-danger px-2 py-1 text-xs text-danger hover:bg-danger/5 disabled:opacity-50"
                      >
                        Cancelar
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {cancel.isError && (
          <p className="mt-2 text-xs text-danger">
            Error cancelando: {(cancel.error as any)?.response?.data?.detail ?? "?"}
          </p>
        )}
      </section>

      <section className="rounded-lg border bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-medium">Colas en Redis</h2>
          <p className="text-xs text-mutedForeground">
            Vaciar una cola descarta las tareas pendientes; las que ya están corriendo siguen.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
          {status?.queues.map((q) => (
            <div key={q.name} className="rounded border p-2 text-sm">
              <p className="text-xs uppercase text-mutedForeground">{q.name}</p>
              <div className="flex items-center justify-between">
                <p className="text-xl font-semibold">{q.pending}</p>
                {q.pending > 0 && (
                  <button
                    onClick={() => {
                      if (confirm(`Vaciar la cola "${q.name}" (${q.pending} tareas)?`)) {
                        purge.mutate(q.name);
                      }
                    }}
                    disabled={purge.isPending}
                    className="rounded border border-danger px-1.5 py-0.5 text-[10px] text-danger hover:bg-danger/5 disabled:opacity-50"
                    title="Descartar tareas pendientes en esta cola"
                  >
                    Vaciar
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 font-medium">Jobs scrapeados</h2>
          {!activity?.recent_jobs.length ? (
            <p className="text-sm text-mutedForeground">Sin actividad reciente.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {activity.recent_jobs.map((j) => (
                <li key={j.id} className="border-b pb-1 last:border-b-0">
                  <p className="font-medium leading-tight">{j.title}</p>
                  <p className="text-xs text-mutedForeground">
                    {j.company ?? "—"} · {j.portal} · {fmtTime(j.scraped_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 font-medium">Matches scoreados</h2>
          {!activity?.recent_matches.length ? (
            <p className="text-sm text-mutedForeground">Sin actividad reciente.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {activity.recent_matches.map((m) => (
                <li key={m.id} className="border-b pb-1 last:border-b-0">
                  <Link to={`/matches/${m.id}`} className="font-medium leading-tight hover:underline">
                    {m.job_title}
                  </Link>
                  <p className="text-xs text-mutedForeground">
                    score {m.fit_score} · {m.status} · {m.portal} · {fmtTime(m.scored_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 font-medium">Materiales generados</h2>
          {!activity?.recent_materials.length ? (
            <p className="text-sm text-mutedForeground">Sin actividad reciente.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {activity.recent_materials.map((m) => (
                <li key={m.id} className="border-b pb-1 last:border-b-0">
                  <Link to={`/matches/${m.match_id}`} className="font-medium hover:underline">
                    {m.type === "cv" ? "CV adaptado" : "Carta"} v{m.version}
                  </Link>
                  <p className="text-xs text-mutedForeground">{fmtTime(m.generated_at)}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <details className="rounded-lg border bg-white p-4 text-sm">
        <summary className="cursor-pointer font-medium">Inspección avanzada (Flower)</summary>
        <div className="mt-3 space-y-2 text-mutedForeground">
          <p>
            Para ver el detalle de cada tarea Celery (argumentos, tracebacks, historial),
            levantá Flower:
          </p>
          <pre className="overflow-x-auto rounded bg-muted p-2 text-xs">
docker compose --profile monitoring up -d flower
          </pre>
          <p>
            Después abrí{" "}
            <a
              href="http://localhost:5555"
              target="_blank"
              rel="noreferrer"
              className="text-primary underline"
            >
              http://localhost:5555
            </a>
            .
          </p>
        </div>
      </details>
    </div>
  );
}
