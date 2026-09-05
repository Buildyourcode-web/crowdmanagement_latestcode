// App Store â€” global app state
import { create } from "zustand";

const initialTheme = (() => {
  try {
    const saved = localStorage.getItem("cc_theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch (e) {}
  return "dark";
})();

// Set initial attribute on HTML tag
if (typeof document !== "undefined") {
  document.documentElement.setAttribute("data-theme", initialTheme);
}

export const useAppStore = create((set, get) => ({
  theme: initialTheme,
  sidebarCollapsed: false,
  fullscreen: false,
  user: { name: "Cmd Officer Sharma", role: "COMMAND_OFFICER", initials: "CS" },
  isAuthenticated: false,

  setTheme: (theme) => {
    try {
      localStorage.setItem("cc_theme", theme);
    } catch (e) {}
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-theme", theme);
    }
    set({ theme });
  },

  toggleTheme: () => {
    const nextTheme = get().theme === "dark" ? "light" : "dark";
    get().setTheme(nextTheme);
  },

  setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  toggleFullscreen: () => set((s) => ({ fullscreen: !s.fullscreen })),
  login: (userData) => set({
    isAuthenticated: true,
    user: userData || { name: "Operator", role: "OPERATOR", initials: "OP" },
  }),
  logout: () => {
    localStorage.removeItem("byc_access_token");
    localStorage.removeItem("byc_refresh_token");
    set({ isAuthenticated: false, user: null });
  },
}));
