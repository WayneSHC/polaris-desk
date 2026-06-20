import type { AlertVM } from "@/types/viewmodel";

// Client-side store for contradiction alerts.
// Persists to sessionStorage so alerts survive same-session navigation.
// Listeners fire synchronously for immediate cross-component updates.

export type ContraAlert = AlertVM & { origin: "contradiction"; cite_key?: string };

const KEY = "polaris_contra_alerts";
type Listener = (alerts: ContraAlert[]) => void;
const listeners = new Set<Listener>();

function read(): ContraAlert[] {
  if (typeof window === "undefined") return [];
  try { return JSON.parse(sessionStorage.getItem(KEY) ?? "[]"); } catch { return []; }
}

function write(alerts: ContraAlert[]) {
  if (typeof window === "undefined") return;
  try { sessionStorage.setItem(KEY, JSON.stringify(alerts)); } catch {}
  listeners.forEach(l => l(alerts));
}

export const contraAlertStore = {
  get: read,
  set: write,
  clear: () => write([]),
  subscribe: (fn: Listener) => {
    listeners.add(fn);
    return () => { listeners.delete(fn); };
  },
};
