// Helper voor account-BFF-routes: haal de ingelogde userid uit de Auth.js-sessie en geef die
// als vertrouwde X-User-Id-header door aan de API. De identiteit komt zo NOOIT uit browser-input.
import { auth } from "@/auth";

export async function sessionUserId(): Promise<string | null> {
  const session = await auth();
  return session?.user?.userid ?? null;
}

export function geenSessie(): Response {
  return Response.json({ detail: "Niet ingelogd." }, { status: 401 });
}
