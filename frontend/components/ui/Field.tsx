interface FieldProps {
  label: string;
  hint?: string;
  required?: boolean;
  error?: string;
  children: React.ReactNode;
}

export function Field({ label, hint, required, error, children }: FieldProps) {
  return (
    <label className="block">
      <span className="mb-1 flex items-baseline gap-1.5 text-sm font-medium text-ink">
        {label}
        {required && <span className="text-fout">*</span>}
        {hint && <span className="ml-auto text-xs font-normal text-faint">{hint}</span>}
      </span>
      {children}
      {error && <span className="mt-1 block text-xs text-fout">{error}</span>}
    </label>
  );
}

// Rijkshuisstijl: formulierveld min. hoogte 48px, lichte radius, lintblauwe focus-ring.
// Geëxporteerd zodat samengestelde velden (zoals de Combobox) dezelfde veldstijl dragen.
export const inputBase =
  "w-full min-h-[48px] rounded-field border border-line bg-paper px-3 py-2 text-sm text-ink placeholder:text-faint focus:border-lint focus:outline-none focus:ring-2 focus:ring-lint/30";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputBase} ${props.className ?? ""}`} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${inputBase} resize-y ${props.className ?? ""}`} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${inputBase} cursor-pointer ${props.className ?? ""}`} />;
}
