import { proxy, readBody } from "@/app/api/_lib/proxy";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const qs = new URL(req.url).search;
  return proxy(`/v1/admin/berichten${qs}`, { admin: true });
}

export async function POST(req: Request) {
  const body = await readBody(req);
  return proxy("/v1/admin/berichten", {
    method: "POST",
    body,
    admin: true,
    headers: { "Content-Type": "application/json" },
  });
}
