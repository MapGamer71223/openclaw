import React, { useEffect, useState } from "react";
import { Routes, Route, Link, useLocation } from "react-router-dom";
import {
  ScanSearch, Gauge, Upload as UploadIcon, FolderSearch, Radar,
  FileBarChart, Menu, X, ChevronRight, Sun, Moon,
} from "lucide-react";
import { Dashboard } from "./pages/Dashboard";
import { Upload } from "./pages/Upload";
import { InvestigationPage } from "./pages/InvestigationPage";
import { api } from "./services/api";
import { useTheme } from "./contexts/ThemeContext";

type NavItem = { to: string; label: string; icon: React.ElementType; end?: boolean };
type NavSection = { section: string; items: NavItem[] };

const NAV: NavSection[] = [
  {
    section: "Investigate",
    items: [
      { to: "/upload", label: "New Investigation", icon: ScanSearch },
    ],
  },
  {
    section: "Analysis",
    items: [
      { to: "/", label: "Dashboard", icon: Gauge, end: true },
      { to: "/", label: "Investigations", icon: FolderSearch },
    ],
  },
  {
    section: "Intelligence",
    items: [
      { to: "/", label: "Timeline & Propagation", icon: Radar },
      { to: "/", label: "Reports", icon: FileBarChart },
    ],
  },
];

function useHealth() {
  const [health, setHealth] = useState<{ status?: string; demo_mode: boolean; openclaw_enabled: boolean } | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const poll = () => api.health().then((h) => { if (!cancelled) { setHealth(h); setError(false); } }).catch(() => { if (!cancelled) setError(true); });
    poll();
    const t = setInterval(poll, 20000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);
  return { health, error };
}

function StatusDot({ ok }: { ok: boolean | null }) {
  return (
    <span
      className={`inline-block w-1.5 h-1.5 rounded-full flex-shrink-0 ${
        ok === null ? "bg-forensic-faint" : ok ? "bg-forensic-success shadow-[0_0_6px_1px_rgba(52,211,153,0.6)]" : "bg-forensic-danger"
      }`}
    />
  );
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <div className="flex items-center justify-between">
      <span className="text-forensic-text2">Appearance</span>
      <div className="inline-flex items-center rounded-lg border border-forensic-border bg-forensic-panel2 p-0.5">
        <button
          type="button"
          onClick={() => setTheme("dark")}
          aria-pressed={theme === "dark"}
          aria-label="Use dark theme"
          className={`flex items-center justify-center w-6 h-6 rounded-md transition-colors focus-ring ${
            theme === "dark" ? "bg-forensic-accent/15 text-forensic-accent" : "text-forensic-muted hover:text-forensic-text2"
          }`}
        >
          <Moon size={13} strokeWidth={2.25} />
        </button>
        <button
          type="button"
          onClick={() => setTheme("light")}
          aria-pressed={theme === "light"}
          aria-label="Use light theme"
          className={`flex items-center justify-center w-6 h-6 rounded-md transition-colors focus-ring ${
            theme === "light" ? "bg-forensic-accent/15 text-forensic-accent" : "text-forensic-muted hover:text-forensic-text2"
          }`}
        >
          <Sun size={13} strokeWidth={2.25} />
        </button>
      </div>
    </div>
  );
}

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const location = useLocation();
  const { health, error } = useHealth();

  const isActive = (item: NavItem) => (item.end ? location.pathname === item.to : location.pathname.startsWith(item.to) && item.to !== "/");

  return (
    <>
      {open && <div className="fixed inset-0 bg-black/60 z-30 lg:hidden" onClick={onClose} />}
      <aside
        className={`fixed lg:sticky top-0 z-40 h-screen w-72 flex-shrink-0 border-r border-forensic-border bg-forensic-panel flex flex-col transition-transform duration-300 ${
          open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        }`}
      >
        <div className="p-5 border-b border-forensic-border flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-forensic-accent/25 to-forensic-violet/20 border border-forensic-accent/30 flex items-center justify-center text-forensic-accent shadow-glow">
              <ScanSearch size={18} strokeWidth={2.25} />
            </div>
            <div>
              <div className="font-bold text-sm text-forensic-text leading-tight tracking-tight">MEDIA FORENSICS</div>
              <div className="text-[10px] text-forensic-muted mono tracking-wide">Digital Investigation Platform</div>
            </div>
          </div>
          <button className="lg:hidden text-forensic-muted hover:text-forensic-text" onClick={onClose} aria-label="Close navigation">
            <X size={18} />
          </button>
        </div>

        <nav className="p-3 flex-1 overflow-y-auto">
          {NAV.map((sec) => (
            <div key={sec.section} className="mb-4">
              <div className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-forensic-faint">{sec.section}</div>
              {sec.items.map((item, i) => {
                const active = isActive(item);
                const Icon = item.icon;
                return (
                  <Link
                    key={sec.section + item.label + i}
                    to={item.to}
                    onClick={onClose}
                    className={`group flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm mb-0.5 transition-all focus-ring ${
                      active
                        ? "bg-forensic-accent/10 text-forensic-accent border border-forensic-accent/25"
                        : "text-forensic-text2 hover:text-forensic-text hover:bg-forensic-panel2 border border-transparent"
                    }`}
                  >
                    <Icon size={16} strokeWidth={2} className={active ? "text-forensic-accent" : "text-forensic-muted group-hover:text-forensic-text2"} />
                    <span className="flex-1">{item.label}</span>
                    {active && <ChevronRight size={14} className="text-forensic-accent/70" />}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="p-4 border-t border-forensic-border text-[11px] space-y-2">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-forensic-faint mb-1.5">System Status</div>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-forensic-text2"><StatusDot ok={!error && !!health} />Detection Engine</span>
            <span className="mono text-forensic-muted">{error ? "Offline" : health ? "Online" : "…"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-forensic-text2"><StatusDot ok={!error && !!health} />Source Search</span>
            <span className="mono text-forensic-muted">{error ? "Offline" : health ? "Online" : "…"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-forensic-text2"><StatusDot ok={health ? health.openclaw_enabled : null} />OpenClaw Agent</span>
            <span className="mono text-forensic-muted">{health ? (health.openclaw_enabled ? "Online" : "Offline") : "…"}</span>
          </div>
          <div className="flex items-center justify-between pt-2 border-t border-forensic-border/60">
            <span className="text-forensic-text2">Mode</span>
            <span className={`mono font-semibold px-1.5 py-0.5 rounded ${health?.demo_mode ? "text-forensic-warn bg-forensic-warn/10" : "text-forensic-success bg-forensic-success/10"}`}>
              {health ? (health.demo_mode ? "DEMO" : "LIVE") : "…"}
            </span>
          </div>
          <div className="pt-2 border-t border-forensic-border/60">
            <ThemeToggle />
          </div>
        </div>
      </aside>
    </>
  );
}

function TopBar({ onMenu }: { onMenu: () => void }) {
  const location = useLocation();
  const title =
    location.pathname === "/upload" ? "New Investigation" :
    location.pathname.startsWith("/investigations/") ? "Investigation" :
    "Dashboard";

  return (
    <header className="sticky top-0 z-20 glass border-b border-forensic-border/80">
      <div className="flex items-center justify-between px-4 sm:px-6 py-3.5">
        <div className="flex items-center gap-3 min-w-0">
          <button className="lg:hidden text-forensic-muted hover:text-forensic-text flex-shrink-0" onClick={onMenu} aria-label="Open navigation">
            <Menu size={20} />
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-[11px] text-forensic-muted mono truncate">
              <span>MEDIA FORENSICS</span>
              <ChevronRight size={12} />
              <span className="text-forensic-text2">{title}</span>
            </div>
            <h2 className="text-base font-semibold text-forensic-text truncate">{title}</h2>
          </div>
        </div>
        <Link
          to="/upload"
          className="flex-shrink-0 inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-forensic-accent text-forensic-bg font-semibold text-sm hover:brightness-110 transition shadow-glow"
        >
          <UploadIcon size={15} strokeWidth={2.5} />
          <span className="hidden sm:inline">New Investigation</span>
        </Link>
      </div>
    </header>
  );
}

export default function App() {
  const [navOpen, setNavOpen] = useState(false);

  return (
    <div className="min-h-screen flex">
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="flex-1 min-w-0 flex flex-col">
        <TopBar onMenu={() => setNavOpen(true)} />
        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/investigations/:id" element={<InvestigationPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
