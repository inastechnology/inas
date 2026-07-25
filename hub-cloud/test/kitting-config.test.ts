import { describe, expect, it } from "vitest";

import { buildGatewayOverlay } from "../scripts/gateway-overlay";

describe("Edge Gateway kitting configuration", () => {
  it("writes only supported runtime fields and keeps expiry in the shipment manifest", () => {
    const expiresAt = "2027-07-23T10:00:00.000Z";
    const overlay = buildGatewayOverlay({
      nodeId: "INAEG-11111111-1111-4111-8111-111111111111",
      parentToken: "A".repeat(43),
      mqttUsername: "edge-111111111111",
      mqttPassword: "mqtt-secret",
      hardwareProfile: "egw-cm4-standard-r1",
      cloudOrigin: "https://cloud-hub.inas-technologies.com",
      tenantPublicId: "tenant-a",
      tenantDisplayName: "Tenant A",
      label: "North field",
      apPassword: "local-ap-password",
      credentialExpiresAt: expiresAt,
    });
    const config = JSON.parse(overlay.get("etc/inas/edge-gateway.json")!.content);
    const shipment = JSON.parse(overlay.get("shipment.json")!.content);

    expect(Object.keys(config).sort()).toEqual(
      [
        "capabilities",
        "data_directory",
        "hardware_profile_id",
        "health",
        "identity_file",
        "mqtt",
        "parent",
        "schema_version",
        "software_version",
      ].sort(),
    );
    expect(shipment.parent_credential_expires_at).toBe(expiresAt);
    expect(JSON.stringify(shipment)).not.toContain("mqtt-secret");
    expect(JSON.stringify(shipment)).not.toContain("A".repeat(43));
  });
});
