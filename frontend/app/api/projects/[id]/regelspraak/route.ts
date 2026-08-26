import { proxy, readBody } from "../../../_lib/proxy";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: Request, { params }: Params) {
  const { id } = await params;
  return proxy(`/v1/projects/${pathSegment(id)}/regelspraak`);
}

export async function POST(req: Request, { params }: Params) {
  const { id } = await params;
  const body = await readBody(req);
  return proxy(`/v1/projects/${pathSegment(id)}/regelspraak`, {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json" },
  });
}
