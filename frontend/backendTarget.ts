// Where the dev server forwards /api and /health: the Aether backend's address.
// The port comes from AETHER_API_PORT — the same line in backend/.env the backend itself uses
// (python -m scripts.serve), so the two always agree. Default 8000.
// 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 (::1) first and each request waited ~2.3 s.

export function backendPort(env: Record<string, string | undefined>): number {
  const raw = env.AETHER_API_PORT?.trim();
  if (!raw) return 8000;
  const port = Number(raw);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`AETHER_API_PORT must be a port number (1-65535), got "${raw}"`);
  }
  return port;
}

export function backendTarget(env: Record<string, string | undefined>): string {
  return `http://127.0.0.1:${backendPort(env)}`;
}
