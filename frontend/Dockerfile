# Dockerfile voor de Wetsanalyse-frontend (Next.js, standalone output).
# Build-context = deze map (frontend/), net als de MCP:
#   docker build -t wetsanalyse-frontend frontend
# De frontend is een BFF: de browser praat alleen met deze server; het API-token blijft
# server-side. De server bereikt de API intern via API_BASE_URL (proxy-netwerk).

# ── Dependencies ──────────────────────────────────────────────────────────────
FROM node:26-slim@sha256:deae974a69e140f44f434ab29cb519fb5f8fe250fd364b8ca446bd0761acdc6a AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

# ── Build ─────────────────────────────────────────────────────────────────────
FROM node:26-slim@sha256:deae974a69e140f44f434ab29cb519fb5f8fe250fd364b8ca446bd0761acdc6a AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# next.config.mjs zet output: 'standalone' → .next/standalone bevat een minimale server.
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM node:26-slim@sha256:deae974a69e140f44f434ab29cb519fb5f8fe250fd364b8ca446bd0761acdc6a AS runtime

ARG GIT_SHA=""
ARG BUILD_TIME=""

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    GIT_SHA=$GIT_SHA \
    BUILD_TIME=$BUILD_TIME

WORKDIR /app

# OS-pakketten patchen (BIO2 / ISO 27002:2022 §8.8), spiegelt de MCP-image.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# De standalone-runtime draait `node server.js` en gebruikt npm nergens. Verwijder npm
# (incl. npx-shims) volledig uit de image: de door npm gebundelde deps (tar, undici, …)
# blijven anders CVE-alerts opleveren in de Trivy-scan zonder ooit te draaien.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx

# Non-root + read-only-fs-proof: lid van groep 0 i.p.v. een eigen gid. De bestanden zijn
# groep-root-eigendom met groep=gebruiker-rechten, zodat de container ook onder een willekeurige UID
# (lid van groep 0) de code kan lezen/uitvoeren. USER 10002.
RUN useradd --no-create-home --uid 10002 --gid 0 nodeapp

# Standalone-server + statische assets. .next/static en public worden niet door de
# standalone-tracer meegekopieerd, dus expliciet plaatsen. Groep-root-eigendom + g=u.
COPY --from=builder --chown=10002:0 /app/.next/standalone ./
COPY --from=builder --chown=10002:0 /app/.next/static ./.next/static
COPY --from=builder --chown=10002:0 /app/public ./public
RUN chgrp -R 0 /app && chmod -R g=u /app

# Entrypoint laadt AUTH_SECRET uit een secret-bestand (file-secret-aanpak; zie docker-entrypoint.sh).
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh

ENV HOME=/tmp
USER 10002

EXPOSE 3000

# Healthcheck via Node's globale fetch (slim-image heeft geen curl).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

# server.js is het entrypoint van de standalone-build; de wrapper zet eerst AUTH_SECRET klaar.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["node", "server.js"]
