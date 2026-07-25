import { describe, expect, it, vi } from "vitest";

import {
  assertRegressionManifest,
  createRegressionRunId,
  ephemeralRegressionNames,
  REGRESSION_MANIFEST_VERSION,
} from "../scripts/regression-guards";

describe("tenant regression destructive-operation guards", () => {
  it("derives every ephemeral identifier from one unpredictable run ID", () => {
    vi.spyOn(crypto, "getRandomValues").mockImplementation((values) => {
      (values as Uint8Array).set([0x01, 0x23, 0x45, 0x67]);
      return values;
    });
    const runId = createRegressionRunId(new Date("2026-07-23T15:00:00.000Z"));
    expect(runId).toBe("20260723t150000z-01234567");
    expect(ephemeralRegressionNames(runId)).toEqual({
      publicId: "reg-e-20260723t150000z-01234567",
      databaseName: "inas-regression-ephemeral-20260723t150000z-01234567",
      customerReference: "regression:ephemeral:20260723t150000z-01234567",
    });
  });

  it("accepts only a manifest whose three tenant identifiers match the run ID", () => {
    const runId = "20260723t150000z-01234567";
    const names = ephemeralRegressionNames(runId);
    expect(
      assertRegressionManifest({
        version: REGRESSION_MANIFEST_VERSION,
        run_id: runId,
        created_at: "2026-07-23T15:00:00.000Z",
        tenant: {
          id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          public_id: names.publicId,
          database_name: names.databaseName,
          customer_reference: names.customerReference,
        },
      }),
    ).toMatchObject({ run_id: runId });
  });

  it("rejects a regular tenant even if a caller edits one manifest field", () => {
    const runId = "20260723t150000z-01234567";
    const names = ephemeralRegressionNames(runId);
    expect(() =>
      assertRegressionManifest({
        version: REGRESSION_MANIFEST_VERSION,
        run_id: runId,
        created_at: "2026-07-23T15:00:00.000Z",
        tenant: {
          id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          public_id: names.publicId,
          database_name: "customer-production",
          customer_reference: names.customerReference,
        },
      }),
    ).toThrow(/exact ephemeral tenant/);
  });
});
