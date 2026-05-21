import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login, loading } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const msg = Array.isArray(detail)
        ? detail.map((d: any) => d?.msg ?? JSON.stringify(d)).join("; ")
        : typeof detail === "string"
        ? detail
        : "No se pudo iniciar sesión";
      setError(msg);
    }
  };

  return (
    <div className="mx-auto mt-12 max-w-sm rounded-lg border bg-white p-6 shadow-sm">
      <h1 className="mb-1 text-xl font-semibold">JobHunter</h1>
      <p className="mb-6 text-sm text-mutedForeground">Iniciar sesión</p>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className="text-sm">Email</label>
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            type="email"
            required
            autoFocus
            className="mt-1 w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring"
          />
        </div>
        <div>
          <label className="text-sm">Contraseña</label>
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            required
            className="mt-1 w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring"
          />
        </div>
        {error && <p className="text-sm text-danger">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-md bg-primary px-3 py-2 text-sm font-medium text-primaryForeground hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "Ingresando…" : "Ingresar"}
        </button>
      </form>
    </div>
  );
}
