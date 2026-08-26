#!/bin/sh
# Laadt AUTH_SECRET (Auth.js) uit een secret-bestand zodat het geheim — net als de andere tokens —
# een BESTAND op de host blijft i.p.v. een plain env in Portainer. Auth.js zelf kent geen
# *_FILE-patroon, dus we exporteren het hier vóór de server start; zo zien zowel de route handlers
# als de edge-middleware (binnen hetzelfde Node-proces) process.env.AUTH_SECRET.
set -e

if [ -z "${AUTH_SECRET:-}" ] && [ -n "${AUTH_SECRET_FILE:-}" ] && [ -f "${AUTH_SECRET_FILE}" ]; then
  AUTH_SECRET="$(cat "${AUTH_SECRET_FILE}")"
  export AUTH_SECRET
fi

exec "$@"
