/**
 * Neon Auth client for this React/Vite app.
 *
 * Uses @neondatabase/auth with BetterAuthReactAdapter so we get:
 *   - authClient.signIn.email()  / signUp.email()  — email/password
 *   - authClient.signIn.social({ provider: "google" }) — OAuth redirect
 *   - authClient.useSession()    — reactive React hook for session state
 *   - authClient.getJWTToken?.() — JWT for backend Bearer auth
 *   - authClient.signOut()       — sign out
 *
 * The session token issued by Neon Auth is a JWT (EdDSA/Ed25519) verifiable
 * by the backend via the JWKS endpoint.
 */
import { createAuthClient } from '@neondatabase/auth';
import { BetterAuthReactAdapter } from '@neondatabase/auth/react/adapters';

const NEON_AUTH_URL = import.meta.env.VITE_NEON_AUTH_URL as string;

if (!NEON_AUTH_URL) {
  console.warn(
    '[neon-auth] VITE_NEON_AUTH_URL is not set — authentication will not work. ' +
    'Add it to your .env file: VITE_NEON_AUTH_URL=<your Neon Auth URL>'
  );
}

export const authClient = createAuthClient(NEON_AUTH_URL ?? '', {
  adapter: BetterAuthReactAdapter(),
});
