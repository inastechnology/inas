export const PUBLIC_TENANT_ID_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789";
export const PUBLIC_TENANT_ID_LENGTH = 10;
export const PUBLIC_TENANT_ID_PATTERN = /^[a-z0-9](?:[a-z0-9-]{4,30}[a-z0-9])$/;

export function normalizePublicTenantId(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (!PUBLIC_TENANT_ID_PATTERN.test(normalized)) {
    throw new Error("public tenant ID must be 6-32 lowercase DNS-safe characters");
  }
  return normalized;
}

export function generatePublicTenantId(): string {
  const bytes = new Uint8Array(PUBLIC_TENANT_ID_LENGTH);
  globalThis.crypto.getRandomValues(bytes);
  return [...bytes].map((byte) => PUBLIC_TENANT_ID_ALPHABET[byte % PUBLIC_TENANT_ID_ALPHABET.length]).join("");
}

export function normalizeEmail(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (
    !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(normalized) ||
    normalized.length > 254 ||
    /[\u0000-\u001f\u007f]/.test(normalized)
  ) {
    throw new Error("email is invalid");
  }
  return normalized;
}
