import Link from "next/link";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

// Rijkshuisstijl: primaire knop in lintblauw, secundaire als lintblauw-outline.
const variants: Record<Variant, string> = {
  primary: "bg-accent text-paper hover:bg-accent-soft border-transparent",
  secondary: "bg-paper text-lint hover:bg-surface border-lint",
  ghost: "bg-transparent text-muted hover:bg-surface hover:text-lint border-transparent",
  danger: "bg-transparent text-fout hover:bg-fout/10 border-fout/40",
};

// Min. hoogte 48px voor primaire/secundaire knoppen (md); sm is compact voor inline-acties.
const sizes: Record<Size, string> = {
  sm: "min-h-[36px] px-3 py-1.5 text-sm",
  md: "min-h-[48px] px-5 py-2 text-sm",
};

const base =
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-button border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export function Button({ variant = "primary", size = "md", className = "", ...props }: ButtonProps) {
  return <button className={`${base} ${sizes[size]} ${variants[variant]} ${className}`} {...props} />;
}

interface LinkButtonProps {
  href: string;
  variant?: Variant;
  size?: Size;
  className?: string;
  onClick?: () => void;
  children: React.ReactNode;
}

export function LinkButton({
  href,
  variant = "primary",
  size = "md",
  className = "",
  onClick,
  children,
}: LinkButtonProps) {
  return (
    <Link href={href} onClick={onClick} className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}>
      {children}
    </Link>
  );
}
