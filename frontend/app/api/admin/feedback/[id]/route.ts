import { proxy } from "@/app/api/_lib/proxy";

export const dynamic = "force-dynamic";

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  return proxy(`/v1/admin/feedback/${encodeURIComponent(id)}`, {
    method: "DELETE",
    admin: true,
  });
}
