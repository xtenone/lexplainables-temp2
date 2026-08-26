#!/usr/bin/env node
/**
 * Wetsanalyse-admin MCP-server (stdio).
 *
 * Ontsluit de bestaande admin-API van de Wetsanalyse-webapp (`/v1/admin/*`) als agent-tools, zodat
 * een MCP-client (Claude Code) de productie-app kan configureren: modelprofielen, gebruikers en de
 * genereerbare API-tokens (read).
 *
 * Config via env (nooit in de repo):
 *   WETSANALYSE_ADMIN_API_URL   — basis-URL van de API, bv. https://api.wetsanalyse.example
 *   WETSANALYSE_ADMIN_TOKEN     — een admin-token (statisch env-token óf een via /beheer gegenereerd token)
 *
 * Fail-closed: zonder beide env-vars weigert de server te starten. Logs (JSON) gaan naar stderr;
 * het token wordt nooit gelogd. stdout is exclusief voor het MCP-protocol.
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

// ── Config ────────────────────────────────────────────────────────────────────

const API_URL = (process.env.WETSANALYSE_ADMIN_API_URL ?? "").replace(/\/+$/, "");
const TOKEN = (process.env.WETSANALYSE_ADMIN_TOKEN ?? "").trim();

// ── Logging (JSON naar stderr; nooit tokens) ───────────────────────────────────

const GEHEIM = new Set(["authorization", "token", "bearer", "secret", "password", "api_key"]);

function log(niveau: "info" | "warn" | "error", bericht: string, velden: Record<string, unknown> = {}): void {
  const schoon: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(velden)) {
    if (GEHEIM.has(k.toLowerCase()) || v === undefined) continue;
    schoon[k] = v;
  }
  process.stderr.write(JSON.stringify({ ts: new Date().toISOString(), niveau, bericht, ...schoon }) + "\n");
}

// ── API-client ──────────────────────────────────────────────────────────────

async function apiFetch(method: string, path: string, body?: unknown): Promise<unknown> {
  const headers: Record<string, string> = { Authorization: `Bearer ${TOKEN}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const tekst = await res.text();
  let data: unknown = tekst;
  try {
    data = tekst ? JSON.parse(tekst) : null;
  } catch {
    /* geen JSON — laat de ruwe tekst staan */
  }
  if (!res.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data
        ? (data as { detail: unknown }).detail
        : tekst;
    throw new Error(`API ${res.status} op ${method} ${path}: ${String(detail).slice(0, 300)}`);
  }
  return data;
}

const seg = (s: string) => encodeURIComponent(s);

// ── Tool-definities (declaratief) ──────────────────────────────────────────────

interface ToolDef {
  name: string;
  description: string;
  input: z.ZodType;
  run: (a: Record<string, unknown>) => Promise<unknown>;
}

const S = z.object;

const TOOLS: ToolDef[] = [
  // — modelprofielen —
  {
    name: "list_profiles",
    description: "Lijst de LLM-modelprofielen.",
    input: S({}),
    run: () => apiFetch("GET", "/v1/admin/profiles"),
  },
  {
    name: "get_profile",
    description: "Haal één modelprofiel op.",
    input: S({ name: z.string() }),
    run: (a) => apiFetch("GET", `/v1/admin/profiles/${seg(a.name as string)}`),
  },
  {
    name: "upsert_profile",
    description: "Maak of werk een modelprofiel bij. api_key is write-only (leeg = ongewijzigd).",
    input: S({
      name: z.string(),
      provider: z.string().optional(),
      model: z.string().optional(),
      api_base: z.string().optional(),
      api_version: z.string().optional(),
      output_strategy: z.string().optional(),
      temperature: z.number().optional(),
      api_key: z.string().optional(),
      is_default: z.boolean().optional(),
    }),
    run: ({ name, ...body }) => apiFetch("PUT", `/v1/admin/profiles/${seg(name as string)}`, body),
  },
  {
    name: "set_default_profile",
    description: "Markeer een modelprofiel als default.",
    input: S({ name: z.string() }),
    run: (a) => apiFetch("POST", `/v1/admin/profiles/${seg(a.name as string)}/default`),
  },
  {
    name: "test_profile",
    description: "Test de verbinding van een modelprofiel (kleine, betaalde LLM-call).",
    input: S({ name: z.string() }),
    run: (a) => apiFetch("POST", `/v1/admin/profiles/${seg(a.name as string)}/test`),
  },
  {
    name: "delete_profile",
    description: "Verwijder een modelprofiel (niet de default).",
    input: S({ name: z.string() }),
    run: async (a) => {
      await apiFetch("DELETE", `/v1/admin/profiles/${seg(a.name as string)}`);
      return { ok: true };
    },
  },
  // — gebruikers —
  {
    name: "list_users",
    description: "Lijst de login-accounts van de webapp.",
    input: S({}),
    run: () => apiFetch("GET", "/v1/admin/users"),
  },
  {
    name: "create_user",
    description: "Maak een gebruiker (tijdelijk wachtwoord wordt eenmalig teruggegeven).",
    input: S({ userid: z.string(), email: z.string(), role: z.enum(["analist", "beheerder"]).optional() }),
    run: ({ userid, email, role }) =>
      apiFetch("POST", "/v1/admin/users", { userid, email, role: role ?? "analist" }),
  },
  {
    name: "patch_user",
    description: "Wijzig rol en/of active-status van een gebruiker.",
    input: S({ userid: z.string(), role: z.enum(["analist", "beheerder"]).optional(), active: z.boolean().optional() }),
    run: ({ userid, ...body }) => apiFetch("PATCH", `/v1/admin/users/${seg(userid as string)}`, body),
  },
  // — API-tokens (read) —
  {
    name: "list_api_tokens",
    description: "Lijst de genereerbare API-tokens (alleen metadata; nooit het token zelf).",
    input: S({}),
    run: () => apiFetch("GET", "/v1/admin/api-tokens"),
  },
];

// ── Server ────────────────────────────────────────────────────────────────────

function alsJsonSchema(schema: z.ZodType): { type: "object"; [k: string]: unknown } {
  const json = z.toJSONSchema(schema, { io: "input" }) as Record<string, unknown>;
  delete json["$schema"];
  return json as { type: "object"; [k: string]: unknown };
}

async function main(): Promise<void> {
  if (!API_URL || !TOKEN) {
    log("error", "Weigering te starten: zet WETSANALYSE_ADMIN_API_URL en WETSANALYSE_ADMIN_TOKEN.");
    process.exit(1);
  }
  const server = new Server(
    { name: "wetsanalyse-admin", version: "0.1.0" },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: TOOLS.map((t) => ({ name: t.name, description: t.description, inputSchema: alsJsonSchema(t.input) })),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    const def = TOOLS.find((t) => t.name === req.params.name);
    if (!def) throw new Error(`Onbekende tool: ${req.params.name}`);
    const args = def.input.parse(req.params.arguments ?? {}) as Record<string, unknown>;
    try {
      const resultaat = await def.run(args);
      log("info", "tool ok", { tool: def.name });
      return { content: [{ type: "text", text: JSON.stringify(resultaat, null, 2) }] };
    } catch (e) {
      log("warn", "tool fout", { tool: def.name, fout: (e as Error).message });
      return { content: [{ type: "text", text: `Fout: ${(e as Error).message}` }], isError: true };
    }
  });

  await server.connect(new StdioServerTransport());
  log("info", "wetsanalyse-admin MCP gestart (stdio)", { api_url: API_URL, tools: TOOLS.length });
}

main().catch((e) => {
  log("error", "fatale startfout", { fout: (e as Error).message });
  process.exit(1);
});
