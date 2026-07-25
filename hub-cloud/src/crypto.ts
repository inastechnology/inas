const TENANT_CREDENTIAL_PREFIX = "v2";
const TENANT_CREDENTIAL_AAD_PREFIX = "inas-tenant-credential:v2";
const NODE_CREDENTIAL_BYTES = 32;
const NODE_SALT_BYTES = 16;

export function base64UrlEncode(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function base64UrlDecode(value: string): Uint8Array {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) {
    throw new Error("value is not valid base64url");
  }
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

export function generateMasterKey(): string {
  return base64UrlEncode(randomBytes(32));
}

export function generateNodeCredential(): { token: string; salt: string } {
  return {
    token: base64UrlEncode(randomBytes(NODE_CREDENTIAL_BYTES)),
    salt: base64UrlEncode(randomBytes(NODE_SALT_BYTES)),
  };
}

export interface TenantCredentialContext {
  tenantId: string;
  databaseName: string;
  databaseUrl: string;
}

export async function encryptTenantCredential(
  masterKey: string,
  context: TenantCredentialContext,
  plaintext: string,
): Promise<string> {
  if (!plaintext) {
    throw new Error("tenant credential must not be empty");
  }
  const key = await importMasterKey(masterKey, ["encrypt"]);
  const iv = randomBytes(12);
  const ciphertext = await globalThis.crypto.subtle.encrypt(
    {
      name: "AES-GCM",
      iv: asArrayBuffer(iv),
      additionalData: tenantCredentialAdditionalData(context),
    },
    key,
    asArrayBuffer(new TextEncoder().encode(plaintext)),
  );
  return `${TENANT_CREDENTIAL_PREFIX}.${base64UrlEncode(iv)}.${base64UrlEncode(new Uint8Array(ciphertext))}`;
}

export async function decryptTenantCredential(
  masterKey: string,
  context: TenantCredentialContext,
  envelope: string,
): Promise<string> {
  const parts = envelope.split(".");
  if (parts.length !== 3 || parts[0] !== TENANT_CREDENTIAL_PREFIX) {
    throw new Error("tenant credential envelope is invalid");
  }
  const key = await importMasterKey(masterKey, ["decrypt"]);
  try {
    const plaintext = await globalThis.crypto.subtle.decrypt(
      {
        name: "AES-GCM",
        iv: asArrayBuffer(base64UrlDecode(parts[1])),
        additionalData: tenantCredentialAdditionalData(context),
      },
      key,
      asArrayBuffer(base64UrlDecode(parts[2])),
    );
    return new TextDecoder().decode(plaintext);
  } catch {
    throw new Error("tenant credential cannot be decrypted");
  }
}

function tenantCredentialAdditionalData(context: TenantCredentialContext): ArrayBuffer {
  for (const [name, value] of Object.entries(context)) {
    if (
      typeof value !== "string" ||
      value.length === 0 ||
      value.length > 500 ||
      /[\u0000\r\n]/.test(value)
    ) {
      throw new Error(`tenant credential ${name} is invalid`);
    }
  }
  return asArrayBuffer(
    new TextEncoder().encode(
      [
        TENANT_CREDENTIAL_AAD_PREFIX,
        context.tenantId,
        context.databaseName,
        context.databaseUrl,
      ].join("\n"),
    ),
  );
}

export async function nodeCredentialDigest(token: string, salt: string): Promise<string> {
  const saltBytes = base64UrlDecode(salt);
  const tokenBytes = new TextEncoder().encode(token);
  const input = new Uint8Array(saltBytes.length + tokenBytes.length);
  input.set(saltBytes);
  input.set(tokenBytes, saltBytes.length);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", asArrayBuffer(input));
  return hexEncode(new Uint8Array(digest));
}

export async function verifyNodeCredential(token: string, salt: string, expectedDigest: string): Promise<boolean> {
  if (!/^[0-9a-f]{64}$/.test(expectedDigest)) {
    return false;
  }
  const actual = await nodeCredentialDigest(token, salt);
  return constantTimeEqual(actual, expectedDigest);
}

export async function sha256Hex(value: string): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", asArrayBuffer(new TextEncoder().encode(value)));
  return hexEncode(new Uint8Array(digest));
}

function randomBytes(length: number): Uint8Array {
  const bytes = new Uint8Array(length);
  globalThis.crypto.getRandomValues(bytes);
  return bytes;
}

async function importMasterKey(masterKey: string, usages: KeyUsage[]): Promise<CryptoKey> {
  const decoded = base64UrlDecode(masterKey);
  if (decoded.length !== 32) {
    throw new Error("TENANT_CREDENTIAL_MASTER_KEY must decode to 32 bytes");
  }
  return globalThis.crypto.subtle.importKey("raw", asArrayBuffer(decoded), { name: "AES-GCM" }, false, usages);
}

function hexEncode(bytes: Uint8Array): string {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function constantTimeEqual(left: string, right: string): boolean {
  if (left.length !== right.length) {
    return false;
  }
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) {
    difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return difference === 0;
}

function asArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer;
}
