# GraphDB — de BWB-kennisgraaf

De kennisgraaf draait op de **docker-host** met de data **lokaal** op
`/var/lib/graphdb/home`. Twee containers plus een back-upcron; geen aparte MCP-server, want
**GraphDB ≥ 11.2 heeft de MCP-server ingebouwd** op `/mcp` (poort 7200). Het nginx'je ervoor doet de
bearer-tokencontrole voor toegang van buiten.

Het netwerk heet expliciet `graphdb_default`, zodat andere stacks (de dev-stack, de importer) er als
extern netwerk op kunnen joinen en GraphDB intern op `http://graphdb:7200` bereiken. **Deploy deze
stack dus vóór de stacks die erop joinen** — anders falen die op een ontbrekend netwerk.

## Waarom de data lokaal staat en niet op netwerkopslag

GraphDB's opslaglaag gebruikt geheugen-gemapte bestanden en file-locking. Over NFS is dat traag en
kan een netwerkhapering stille indexcorruptie geven; Ontotext raadt netwerkopslag voor de
datadirectory af. Wil je de opslag tóch fysiek op de NAS, gebruik dan een **iSCSI-LUN** (blockdevice
met correcte locking) in plaats van een NFS-bind.

## Deployen

Via `.github/workflows/deploy-graaf.yml` (handmatig of bij wijzigingen in `deploy/graphdb/**`). Die
deployt de graphdb-stack en de importer in de juiste volgorde en controleert daarna of de repository
`inning` antwoordt. Handmatig via Portainer kan ook, met deze env:

| var | waarde |
|---|---|
| `MCP_BEARER_TOKEN` | hetzelfde token als `secrets.GRAPHDB_TOKEN` in GitHub — anders komt graph-qa er niet in |
| `GRAPHDB_SVC_USER` / `GRAPHDB_SVC_PASSWORD` | het service-account (zie *Beveiliging*) |
| `GRAPHDB_BASIC` | base64 van `user:wachtwoord`, voor de nginx-header |
| `GRAPHDB_HEAP` | `2g`; bij een host met 4 GB RAM liever `1500m` — GraphDB claimt de heap hard |

Controleren:

```bash
curl -s -u <user>:<wachtwoord> http://<docker-host>:7200/rest/repositories | jq -r '.[].id'  # inning
curl -s -o /dev/null -w '%{http_code}\n' http://<docker-host>:8004/mcp                       # 401 = goed
```

Wil je de graaf van buiten bereikbaar maken (bijvoorbeeld voor een MCP-client), maak dan in
nginx-proxy-manager een host voor de MCP-poort → `<docker-host>:8004` met `proxy_buffering off;`.

## Beveiliging

**GraphDB-security staat aan**: zonder credentials komt niemand bij de graaf, ook niet vanaf het LAN.
Twee accounts:

| account | rechten | gebruikt door |
|---|---|---|
| `admin` | `ROLE_ADMIN` | beheer via de GraphDB-workbench-UI |
| `wetsanalyse` | lezen + schrijven op `inning` | de auth-proxy, de back-upcron en de importer |

De wachtwoorden staan **niet in de repo**: ze komen als stack-env (`GRAPHDB_SVC_USER`/
`GRAPHDB_SVC_PASSWORD`, plus `GRAPHDB_BASIC`) en horen in Vaultwarden.

Wie praat hoe met de graaf:

- **graph-qa** → `mcp-auth-proxy:8004` met zijn bearer-token; de proxy controleert dat token en
  **vervangt** de header door het service-account. De agent kent de GraphDB-credentials dus niet.
- **de importer en de back-upcron** → rechtstreeks `graphdb:7200` met het service-account.
- **de healthcheck** → met dezelfde credentials; zonder dat geeft `/rest/repositories` 401 en zou de
  container onterecht unhealthy zijn.
- **jij** → de GraphDB-workbench, met GraphDB's eigen loginscherm. Zet daar géén basic-auth in
  nginx-proxy-manager vóór: twee `Authorization`-headers op één pad botsen met de GraphDB-login.

> **Security tijdelijk uitzetten** (als iets vastloopt): `curl -u admin:<wachtwoord> -X POST
> http://<docker-host>:7200/rest/security -H 'Content-Type: application/json' -d 'false'`.

## BWB's importeren

De importservice draait naast de graaf op dezelfde host: stack **`bwb-import`**, broncode in
`tools/bwb-import/`, image via GHCR. Zie `deploy/bwb-import/README.md` voor het aanroepen.

## Back-up — twee lagen

**1. RDF-dump, dagelijks 03:00** — service `graphdb-backup` in deze stack. Exporteert de repository
als **N-Quads** (houdt de named graphs vast; TriG/Turtle zou de contexts verliezen) naar
`/var/lib/graphdb/backup/inning-<datum>.nq.gz`, retentie 7. De dump schrijft naar `.tmp` en
hernoemt pas bij succes, zodat een afgebroken run geen half bestand achterlaat dat er als geldige
back-up uitziet. Log: `/var/lib/graphdb/backup/backup.log`.

**2. een host-back-up van de hele machine** — wat je hypervisor of VM-platform daarvoor ook biedt.
Plan die **ná** de RDF-dump, zodat de verse dump meelift in de host-back-up.

Waarom allebei: een host-back-up maakt een snapshot op filesystem-niveau — consistent voor het
bestandssysteem, maar GraphDB kan midden in een schrijfactie zitten. De RDF-export is per definitie
applicatie-consistent. De host-back-up geeft de hele machine terug, de dump geeft gegarandeerd
leesbare data.

Handmatig een dump draaien:

```bash
docker exec graphdb-backup /usr/local/bin/dump.sh
```

### Herstellen

De RDF-dump is **getest teruggezet**: geladen in een tijdelijke repository leverde hij 388.161
triples op, gelijk aan productie, met de juiste inhoud op een steekproef (artikel 2 lid 1 onderdeel
k). Herladen duurde 7,5 seconde.

Uit de **host-back-up**: de hele machine terug, inclusief afgeleide structuren.

Uit de **RDF-dump**: maak een lege repository `inning` en laad de quads:

```bash
zcat inning-<datum>.nq.gz | curl -X POST -u <user>:<wachtwoord> \
  -H 'Content-Type: application/n-quads' \
  --data-binary @- http://<docker-host>:7200/repositories/inning/statements
```

> Let op: een RDF-dump bevat de triples, maar niet de **afgeleide** structuren — met name de
> similarity-index `bwb_similarity` (die graph-qa nodig heeft voor `semantic_search`) moet daarna
> opnieuw gebouwd worden. Uit de host-back-up komt die wél mee.
