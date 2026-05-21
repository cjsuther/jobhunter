import { useEffect } from "react";
import { Navigate, Route, Routes, Link, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import MatchDetailPage from "@/pages/MatchDetailPage";
import TrackingPage from "@/pages/TrackingPage";
import QueuePage from "@/pages/QueuePage";
import ScrapersPage from "@/pages/ScrapersPage";
import SettingsPage from "@/pages/SettingsPage";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { me } = useAuth();
  const loc = useLocation();
  if (!localStorage.getItem("access_token")) {
    return <Navigate to="/login" state={{ from: loc }} replace />;
  }
  if (!me) return <div className="p-6 text-mutedForeground">Cargando…</div>;
  return <>{children}</>;
}

function NavBar() {
  const { me, logout } = useAuth();
  if (!me) return null;
  return (
    <nav className="border-b bg-white">
      <div className="container flex h-14 items-center justify-between">
        <div className="flex items-center gap-6">
          <span className="font-semibold">JobHunter</span>
          <Link to="/dashboard" className="text-sm hover:underline">Dashboard</Link>
          <Link to="/tracking" className="text-sm hover:underline">Tracking</Link>
          <Link to="/queue" className="text-sm hover:underline">Cola</Link>
          <Link to="/scrapers" className="text-sm hover:underline">Scrapers</Link>
          <Link to="/settings" className="text-sm hover:underline">Settings</Link>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-mutedForeground">{me.email}</span>
          <button
            onClick={() => {
              logout();
              window.location.assign("/login");
            }}
            className="rounded-md border px-2 py-1 hover:bg-muted"
          >
            Salir
          </button>
        </div>
      </div>
    </nav>
  );
}

export default function App() {
  const { fetchMe } = useAuth();
  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  return (
    <div className="min-h-screen bg-muted/30">
      <NavBar />
      <main className="container py-6">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/dashboard"
            element={
              <RequireAuth>
                <DashboardPage />
              </RequireAuth>
            }
          />
          <Route
            path="/matches/:id"
            element={
              <RequireAuth>
                <MatchDetailPage />
              </RequireAuth>
            }
          />
          <Route
            path="/tracking"
            element={
              <RequireAuth>
                <TrackingPage />
              </RequireAuth>
            }
          />
          <Route
            path="/queue"
            element={
              <RequireAuth>
                <QueuePage />
              </RequireAuth>
            }
          />
          <Route
            path="/scrapers"
            element={
              <RequireAuth>
                <ScrapersPage />
              </RequireAuth>
            }
          />
          <Route
            path="/settings"
            element={
              <RequireAuth>
                <SettingsPage />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </main>
    </div>
  );
}
