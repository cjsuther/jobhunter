import { create } from "zustand";
import { api } from "./api";

export type Me = { id: string; email: string; role: string; full_name?: string | null };

type AuthState = {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  fetchMe: () => Promise<void>;
};

export const useAuth = create<AuthState>((set) => ({
  me: null,
  loading: false,
  login: async (email, password) => {
    set({ loading: true });
    try {
      const r = await api.post("/auth/login", { email, password });
      localStorage.setItem("access_token", r.data.access_token);
      localStorage.setItem("refresh_token", r.data.refresh_token);
      const me = await api.get("/auth/me");
      set({ me: me.data });
    } finally {
      set({ loading: false });
    }
  },
  logout: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    set({ me: null });
  },
  fetchMe: async () => {
    if (!localStorage.getItem("access_token")) return;
    try {
      const r = await api.get("/auth/me");
      set({ me: r.data });
    } catch {
      set({ me: null });
    }
  },
}));
