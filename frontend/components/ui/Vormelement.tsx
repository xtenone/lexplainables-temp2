// Rijkshuisstijl-vormelement: een vlak met één grote afgeronde hoek als signatuur.
// Bewust spaarzaam inzetten (max. 3× per scherm, above the fold) en de radius niet animeren.
export function Vormelement({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-button rounded-br-vorm bg-lint text-paper ${className}`}>
      {children}
    </div>
  );
}
