import type { BerichtType } from "@/lib/types";

const TYPE_LABEL: Record<BerichtType, string> = {
  info:         "Informatie",
  update:       "Update",
  waarschuwing: "Waarschuwing",
  kritiek:      "Kritiek",
};

const TYPE_STIJL: Record<BerichtType, string> = {
  info:         "bg-info/10 text-info border-info/20",
  update:       "bg-succes/10 text-succes border-succes/20",
  waarschuwing: "bg-waarschuwing/10 text-waarschuwing border-waarschuwing/20",
  kritiek:      "bg-fout/10 text-fout border-fout/20",
};

export function BerichtBadge({ type }: { type: BerichtType }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-xs font-medium ${TYPE_STIJL[type]}`}
    >
      {TYPE_LABEL[type]}
    </span>
  );
}
