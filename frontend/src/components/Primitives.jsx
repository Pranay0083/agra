export const Panel = ({ title, right, children, className = "", testId }) => (
  <section
    data-testid={testId}
    className={`border border-[#1a1a1a] bg-[#0a0a0a] ${className}`}
  >
    {(title || right) && (
      <header className="flex items-center justify-between gap-3 border-b border-[#1a1a1a] px-4 py-2.5">
        <h3 className="text-xs uppercase tracking-[0.2em] text-[#9ca3af]">{title}</h3>
        {right}
      </header>
    )}
    <div className="p-4">{children}</div>
  </section>
);

export const Metric = ({ label, value, sub, accent = "#f3f4f6", testId }) => (
  <div
    data-testid={testId}
    className="border border-[#1a1a1a] bg-[#0a0a0a] p-4 transition-colors duration-150 hover:border-[#333]"
  >
    <div className="text-[10px] uppercase tracking-[0.22em] text-[#6b7280]">{label}</div>
    <div
      className="mt-2 font-[Chivo] text-3xl font-black leading-none"
      style={{ color: accent }}
    >
      {value}
    </div>
    {sub && <div className="mt-1.5 text-[11px] text-[#6b7280]">{sub}</div>}
  </div>
);

export const Tag = ({ children, color = "#6b7280", solid = false, testId }) => (
  <span
    data-testid={testId}
    className="inline-flex items-center px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em]"
    style={
      solid
        ? { background: color, color: "#050505", fontWeight: 700 }
        : { border: `1px solid ${color}55`, color }
    }
  >
    {children}
  </span>
);

export const Empty = ({ title, hint, action }) => (
  <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
    <div className="font-[Chivo] text-lg font-black text-[#3d3d3d]">{"[ "}{title}{" ]"}</div>
    {hint && <p className="max-w-md text-xs leading-relaxed text-[#6b7280]">{hint}</p>}
    {action}
  </div>
);
