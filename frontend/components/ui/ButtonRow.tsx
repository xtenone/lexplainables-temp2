import type { ReactNode } from "react";

type Align = "start" | "end" | "between";

const justify: Record<Align, string> = {
  start: "sm:justify-start",
  end: "sm:justify-end",
  between: "sm:justify-between",
};

// Consistente actie-knoppenrij: op mobiel stapelen de knoppen volle-breedte onder elkaar,
// op desktop (sm+) staan ze naast elkaar op hun natuurlijke breedte. De breedte wordt op de
// container gestuurd ([&>*] = elke directe knop), zodat losse knoppen geen eigen className nodig
// hebben en inline-knoppen elders ongemoeid blijven.
export function ButtonRow({
  align = "end",
  className = "",
  children,
}: {
  align?: Align;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={`flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center ${justify[align]} [&>*]:w-full sm:[&>*]:w-auto ${className}`}
    >
      {children}
    </div>
  );
}
