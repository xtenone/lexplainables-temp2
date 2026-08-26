#!/usr/bin/env bash
# Schrijft het OpenAPI-schema van deze service weg naar api/generated/openapi.json
# (werkwijze-ADR-0011, docs/project/architectuur/stack-profiel.md §Contractgeneratie).
#
# Dit is de "ene bron" -> schema-stap: de frontend genereert daaruit vervolgens zijn eigen
# TypeScript-types via een relatief pad, zolang beide services in dezelfde monorepo staan
# (werkwijze-ADR-0017). Draai dit script opnieuw na elke wijziging aan een `models.py`/
# `contracts.py` van een feature; bewerk `generated/openapi.json` nooit met de hand.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

mkdir -p generated

uv run python -c "
import json
from app.main import app

with open('generated/openapi.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2, sort_keys=True)
    f.write('\n')
"

echo "Geschreven: api/generated/openapi.json"
