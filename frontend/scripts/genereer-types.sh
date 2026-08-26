#!/usr/bin/env bash
# Genereert frontend/generated/types.ts uit api/generated/openapi.json (werkwijze-ADR-0017,
# docs/project/architectuur/stack-profiel.md §Contractgeneratie).
#
# Leest via een relatief pad rechtstreeks het schema van de `api`-service, zolang beide services
# in dezelfde monorepo staan. Draai eerst `api/scripts/genereer-types.sh` als het schema nog niet
# (opnieuw) is weggeschreven. Bewerk `generated/types.ts` nooit met de hand.
#
# Let op: dit bestand wordt nog door niets in de frontend geïmporteerd. De frontend blijft
# bewust byte-voor-byte gelijk aan wetsanalyse-ai totdat de frontend zelf wordt aangepast (zie
# de projectroot-CLAUDE.md) — dit script + zijn uitvoer staan alvast klaar voor dat moment.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

SCHEMA="../api/generated/openapi.json"

if [ ! -f "$SCHEMA" ]; then
  echo "Schema niet gevonden: $SCHEMA — draai eerst api/scripts/genereer-types.sh" >&2
  exit 1
fi

mkdir -p generated

npx --yes openapi-typescript "$SCHEMA" -o generated/types.ts

echo "Geschreven: frontend/generated/types.ts"
