import { proxy, readBody } from "@/app/api/_lib/proxy";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

export async function PUT(req: Request, { params }: Params) {
  const { id } = await params;
  const body = await readBody(req);
  return proxy(`/v1/admin/berichten/${encodeURIComponent(id)}`, {
    method: "PUT",
    body,
    admin: true,
    headers: { "Content-Type": "application/json" },
  });
}

export async function DELETE(_req: Request, { params }: Params) {
  const { id } = await params;
  return proxy(`/v1/admin/berichten/${encodeURIComponent(id)}`, { method: "DELETE", admin: true });
}
