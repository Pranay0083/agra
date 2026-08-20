import { NavLink, useLocation } from "react-router-dom";
import {
  Broadcast,
  ChartLineUp,
  Gear,
  ShieldCheck,
  Stack,
  TerminalWindow,
  Books,
} from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { TID } from "@/constants/testIds";

const NAV = [
  { to: "/", label: "Overview", icon: Broadcast, tid: TID.nav.overview, end: true },
  { to: "/reviews", label: "Reviews", icon: Stack, tid: TID.nav.reviews },
  { to: "/simulator", label: "Run Review", icon: TerminalWindow, tid: TID.nav.simulator },
  { to: "/analytics", label: "Analytics", icon: ChartLineUp, tid: TID.nav.analytics },
  { to: "/policies", label: "RAG Policies", icon: Books, tid: TID.nav.policies },
  { to: "/settings", label: "Settings", icon: Gear, tid: TID.nav.settings },
];

const Dot = ({ ok }) => (
  <span
    className="inline-block h-1.5 w-1.5"
    style={{ background: ok ? "#34c759" : "#ff3b30" }}
    aria-hidden="true"
  />
);

export const Layout = ({ children }) => {
  const location = useLocation();
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: async () => (await api.get("/system/health")).data,
    refetchInterval: 60000,
  });

  return (
    <div className="grain min-h-screen bg-[#050505] text-[#f3f4f6]">
      <div className="flex min-h-screen">
        <aside className="sticky top-0 z-20 flex h-screen w-[62px] shrink-0 flex-col border-r border-[#1a1a1a] bg-[#0a0a0a] lg:w-[236px]">
          <div className="flex h-[62px] items-center gap-2.5 border-b border-[#1a1a1a] px-4">
            <ShieldCheck size={22} weight="duotone" color="#ff3b30" />
            <div className="hidden lg:block">
              <div className="font-[Chivo] text-[13px] font-black leading-none tracking-tight">
                SENTRY&nbsp;GRAPH
              </div>
              <div className="mt-1 text-[9px] uppercase tracking-[0.24em] text-[#6b7280]">
                PR Security Agent
              </div>
            </div>
          </div>

          <nav className="flex-1 py-2">
            {NAV.map(({ to, label, icon: Icon, tid, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                data-testid={tid}
                className={({ isActive }) =>
                  `group relative flex items-center gap-3 border-l-2 px-4 py-3 text-xs uppercase tracking-[0.14em] transition-colors duration-150 ${
                    isActive
                      ? "border-l-[#ff3b30] bg-[#121212] text-[#f3f4f6]"
                      : "border-l-transparent text-[#6b7280] hover:border-l-[#333] hover:bg-[#0f0f0f] hover:text-[#f3f4f6]"
                  }`
                }
              >
                <Icon size={17} weight="regular" />
                <span className="hidden lg:inline">{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="hidden border-t border-[#1a1a1a] px-4 py-3 lg:block">
            <div className="mb-2 text-[9px] uppercase tracking-[0.24em] text-[#6b7280]">
              Runtime
            </div>
            <ul className="space-y-1.5 text-[10px] text-[#9ca3af]">
              <li className="flex items-center gap-2">
                <Dot ok={health?.gemini?.ok} /> {health?.gemini?.model || "gemini"}
              </li>
              <li className="flex items-center gap-2">
                <Dot ok={health?.supabase?.ready} /> supabase pgvector
              </li>
              <li className="flex items-center gap-2">
                <Dot ok={health?.github?.ok} /> github {health?.github?.login || ""}
              </li>
              <li className="flex items-center gap-2">
                <Dot ok={Object.values(health?.linters || {}).some(Boolean)} /> mcp linters
              </li>
            </ul>
          </div>
        </aside>

        <main className="relative z-10 min-w-0 flex-1">
          <div className="hairline-grid min-h-screen">
            <div key={location.pathname} className="rise mx-auto max-w-[1560px] px-5 py-6 lg:px-8 lg:py-8">
              {children}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
