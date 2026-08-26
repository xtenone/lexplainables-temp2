import { proxy } from "@/app/api/_lib/proxy";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const qs = new URL(req.url).search;
  return proxy(`/v1/annotatie/documenten${qs}`);
}

export async function POST(req: Request) {
  return proxy(`/v1/annotatie/documenten`, {
    method: "POST",
    body: await req.text(),
    headers: { "Content-Type": "application/json" },
  });
}
