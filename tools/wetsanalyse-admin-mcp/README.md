# wetsanalyse-admin-mcp

Een **stdio-MCP-server** die de bestaande admin-API van de Wetsanalyse-webapp (`/v1/admin/*`) als
agent-tools ontsluit, zodat een MCP-client (Claude Code) de app kan configureren: modelprofielen,
gebruikers en de genereerbare API-tokens (read). Het *wrapt* de admin-API — er is geen tweede
configuratie-API.

Draait **lokaal** (op jouw machine) wanneer je Claude Code draait en praat over HTTPS met de API met
een admin-token. Het is dus sessie-tooling, geen standing verbinding. Logs (JSON) gaan naar stderr;
het token wordt nooit gelogd.

## Tools

`list_profiles`, `get_profile`, `upsert_profile`, `set_default_profile`, `test_profile`,
`delete_profile`, `list_users`, `create_user`, `patch_user`, `list_api_tokens`.

(Genereren/intrekken van API-tokens zit bewust **niet** in de MCP — dat blijft de `/beheer`-UI, om de
blast-radius klein te houden.)

## Bouwen

```bash
cd tools/wetsanalyse-admin-mcp
npm install
npm run build      # → dist/ (gecommit, zodat `node dist/index.js` zonder buildstap werkt)
```

## Activeren (koppelen aan productie)

1. **Genereer een token** in de webapp: `/beheer` → **API-tokens** → *Token genereren* (label bijv.
   `claude-admin-mcp`). Het volledige token wordt **één keer** getoond — kopieer het.
2. **Zet het token** als env-var voor Claude Code. In `.claude/settings.local.json` (gitignored,
   machine-lokaal — dezelfde plek als `WETTENBANK_TOKEN`):

   ```json
   "env": {
     "WETSANALYSE_ADMIN_TOKEN": "wa_admin_…het-gegenereerde-token…"
   }
   ```

   De **registratie van de server is machine-lokaal**, niet gecommit: deze repo is publiek en een
   `.mcp.json` erin zou de API-URL van je omgeving prijsgeven. Registreer hem dus zelf, met je eigen
   URL:

   ```bash
   claude mcp add wetsanalyse-admin -- node tools/wetsanalyse-admin-mcp/dist/index.js
   ```

   en zet `WETSANALYSE_ADMIN_API_URL` in dezelfde `env`-sectie als het token hierboven.
3. **Verifieer**: `claude mcp list` → `wetsanalyse-admin` verbonden. Vraag Claude bijv. de
   modelprofielen te tonen (`list_profiles`).

Roteren = het token intrekken in `/beheer` en een nieuw genereren. Verlies je toegang, dan trek je het
in — de MCP kan er niets meer mee.

## Env

| Var | Verplicht | Betekenis |
|-----|-----------|-----------|
| `WETSANALYSE_ADMIN_API_URL` | ja | Basis-URL van de API (bv. `https://api.wetsanalyse.example`). Machine-lokaal zetten. |
| `WETSANALYSE_ADMIN_TOKEN`   | ja | Admin-token (env-token óf een via `/beheer` gegenereerd token). Uit je lokale env. |

Zonder beide weigert de server te starten (fail-closed).

---

## Grafana-MCP (aparte, officiële server)

Voor het inrichten van Grafana (datasources/dashboards/alerting) gebruik je de **officiële**
`mcp/grafana`-server — geen eigen build, en net als hierboven **machine-lokaal geregistreerd** in
plaats van gecommit. Twee stappen:

1. **Grafana service-account + token**: in Grafana → *Administration → Users and access → Service
   accounts* → nieuw account (rol *Editor* of *Admin*) → *Add service account token*. Kopieer het.
2. Registreer de server lokaal met jouw Grafana-URL en het token uit stap 1:

   ```bash
   claude mcp add grafana \
     -e GRAFANA_URL=https://grafana.example \
     -e GRAFANA_SERVICE_ACCOUNT_TOKEN=glsa_… \
     -- docker run --rm -i -e GRAFANA_URL -e GRAFANA_SERVICE_ACCOUNT_TOKEN mcp/grafana -t stdio
   ```

3. `claude mcp list` → `grafana` verbonden. De observability-stack is al gebouwd in
   `deploy/observability/` (Collector + Tempo/Loki/Prometheus + Alloy, dashboard, alerting); via de
   MCP beheer je de datasources, het dashboard en de alertregels. Zie `docs/observability.md`.
