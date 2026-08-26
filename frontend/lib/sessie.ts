// Pure sessie-helper (geen server-only imports → los te unit-testen).

/** Is een JWT-sessie gerevoceerd? Waar als het inlogmoment (`loginAt`, ms) vóór de account-epoch
 *  (`sessionsValidFrom`, ms) ligt — bv. na een wachtwoordwijziging. Geen epoch (nooit gewijzigd) →
 *  nooit gerevoceerd. */
export function sessieGerevoceerd(loginAt: unknown, sessionsValidFrom?: number): boolean {
  if (!sessionsValidFrom) return false;
  const l = typeof loginAt === "number" ? loginAt : 0;
  return l < sessionsValidFrom;
}
