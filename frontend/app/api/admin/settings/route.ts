import { proxy, readBody } from "../../_lib/proxy";

export const dynamic = "force-dynamic";

export async function GET() {
  return proxy("/v1/admin/settings", { admin: true });
}

export async function PUT(req: Request) {
  const body = await readBody(req);
  return proxy("/v1/admin/settings", {
    method: "PUT",
    body,
    admin: true,
    headers: { "Content-Type": "application/json" },
  });
}
