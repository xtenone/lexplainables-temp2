export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-button border border-line bg-surface ${className}`}>{children}</div>
  );
}

export function Section({
  title,
  subtitle,
  count,
  level = 2,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  count?: number;
  /** Kop-niveau binnen de pagina-hiërarchie: 2 = sectie (default), 3 = subsectie onder een fase-kop. */
  level?: 2 | 3;
  children: React.ReactNode;
  className?: string;
}) {
  const Heading = level === 3 ? "h3" : "h2";
  const headingClass =
    level === 3
      ? "font-display text-base font-semibold text-lint"
      : "font-display text-lg font-semibold text-lint";
  return (
    <section className={`animate-rise ${className}`}>
      <div className="mb-4 flex items-baseline gap-3 border-b border-line pb-2">
        <Heading className={headingClass}>{title}</Heading>
        {typeof count === "number" && (
          <span className="font-mono text-xs text-faint">{count}</span>
        )}
        {subtitle && <span className="ml-auto text-xs text-faint">{subtitle}</span>}
      </div>
      {children}
    </section>
  );
}
