export const REGRESSION_MANIFEST_VERSION = 1;
export const PERSISTENT_PUBLIC_ID = "regression-baseline";
export const PERSISTENT_DATABASE_NAME = "inas-regression-baseline";
export const PERSISTENT_CUSTOMER_REFERENCE = "regression:persistent:v1";
// The public route accepts at most 32 characters. "reg-e-" + the 25-character
// run ID stays within that boundary while the DB/reference retain descriptive names.
export const EPHEMERAL_PUBLIC_ID_PREFIX = "reg-e-";
export const EPHEMERAL_DATABASE_PREFIX = "inas-regression-ephemeral-";
export const EPHEMERAL_CUSTOMER_REFERENCE_PREFIX = "regression:ephemeral:";

const RUN_ID = /^[0-9]{8}t[0-9]{6}z-[a-f0-9]{8}$/;

export interface RegressionManifest {
  version: 1;
  run_id: string;
  created_at: string;
  tenant: {
    id: string;
    public_id: string;
    database_name: string;
    customer_reference: string;
  };
}

export function createRegressionRunId(now = new Date()): string {
  const timestamp = now
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}Z$/, "z")
    .toLowerCase();
  const random = new Uint8Array(4);
  crypto.getRandomValues(random);
  return `${timestamp}-${[...random].map((value) => value.toString(16).padStart(2, "0")).join("")}`;
}

export function ephemeralRegressionNames(runId: string): {
  publicId: string;
  databaseName: string;
  customerReference: string;
} {
  assertRunId(runId);
  return {
    publicId: `${EPHEMERAL_PUBLIC_ID_PREFIX}${runId}`,
    databaseName: `${EPHEMERAL_DATABASE_PREFIX}${runId}`,
    customerReference: `${EPHEMERAL_CUSTOMER_REFERENCE_PREFIX}${runId}`,
  };
}

export function assertRegressionManifest(value: unknown): RegressionManifest {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("regression manifest must be an object");
  }
  const manifest = value as Partial<RegressionManifest>;
  assertRunId(manifest.run_id);
  const names = ephemeralRegressionNames(manifest.run_id);
  if (
    manifest.version !== REGRESSION_MANIFEST_VERSION ||
    typeof manifest.created_at !== "string" ||
    !Number.isFinite(Date.parse(manifest.created_at)) ||
    typeof manifest.tenant !== "object" ||
    manifest.tenant === null ||
    typeof manifest.tenant.id !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
      manifest.tenant.id,
    ) ||
    manifest.tenant.public_id !== names.publicId ||
    manifest.tenant.database_name !== names.databaseName ||
    manifest.tenant.customer_reference !== names.customerReference
  ) {
    throw new Error("regression manifest does not identify an exact ephemeral tenant");
  }
  return manifest as RegressionManifest;
}

export function assertRunId(value: unknown): asserts value is string {
  if (typeof value !== "string" || !RUN_ID.test(value)) {
    throw new Error("regression run ID is invalid");
  }
}
