import { proxy, readBody } from "@/app/api/_lib/proxy";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

export async function PATCH(req: Request, { params }: Params) {
  const { id } = await params;
  const body = await readBody(req);
  return proxy(`/v1/admin/berichten/${encodeURIComponent(id)}/publicatie`, {
    method: "PATCH",
    body,
    admin: true,
    headers: { "Content-Type": "application/json" },
  });
}
