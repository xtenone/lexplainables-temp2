// Type-uitbreiding: de userid (inlog-identiteit) + rol op de sessie/JWT/user (zie auth.config.ts).
import type { Role } from "@/auth.config";
import type { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    user: { userid?: string; role?: Role } & DefaultSession["user"];
  }
  interface User {
    userid?: string;
    role?: Role;
    /** "Ingelogd blijven op dit apparaat": bepaalt de sessieduur (30 d vs 12 u). */
    rememberMe?: boolean;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    userid?: string;
    role?: Role;
    rememberMe?: boolean;
    /** Laatste herverificatie tegen de API (ms); begrenst het herverificatie-interval. */
    verifiedAt?: number;
    /** Inlogmoment (ms): sessie-revocatie verwerpt tokens ouder dan de account-epoch. */
    loginAt?: number;
  }
}
