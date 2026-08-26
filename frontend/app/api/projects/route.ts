import { proxy, readBody } from "../_lib/proxy";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const qs = url.search ? url.search : "";
  return proxy(`/v1/projects${qs}`);
}

export async function POST(req: Request) {
  const body = await readBody(req);
  return proxy(`/v1/projects`, {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json" },
  });
}
