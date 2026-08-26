// Publieke BFF-route voor de eenmalige registratie (vóór er een sessie bestaat).
// GET  → is registratie nog open? · POST → maak de allereerste beheerder.
// De API sluit /v1/auth/setup zodra er een account bestaat (409).
import { proxy, readBody } from "../_lib/proxy";

export const dynamic = "force-dynamic";

export async function GET() {
  return proxy(`/v1/auth/setup-status`);
}

export async function POST(req: Request) {
  const body = await readBody(req);
  return proxy(`/v1/auth/setup`, {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json" },
  });
}
