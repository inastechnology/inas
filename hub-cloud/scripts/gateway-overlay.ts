import { qrSvg, wifiQrPayload } from "./qrcode";

export interface GatewayOverlayValues {
  nodeId: string;
  parentToken: string;
  mqttUsername: string;
  mqttPassword: string;
  hardwareProfile: string;
  cloudOrigin: string;
  tenantPublicId: string;
  tenantDisplayName: string;
  label: string;
  apPassword: string;
  credentialExpiresAt: string;
}

export function buildGatewayOverlay(
  values: GatewayOverlayValues,
): Map<string, { content: string; mode: number }> {
  const apSsid = `INAS-${values.nodeId.slice(-8).toUpperCase()}`;
  const cloudHubUrl = `${values.cloudOrigin}/t/${values.tenantPublicId}/`;
  const apWifiPayload = wifiQrPayload(apSsid, values.apPassword);
  const identity = {
    schema_version: 1,
    node_id: values.nodeId,
    node_type: "edge_gateway",
  };
  const config = {
    schema_version: 1,
    data_directory: "/var/lib/inas",
    identity_file: "/var/lib/inas/identity.json",
    hardware_profile_id: values.hardwareProfile,
    software_version: "0.1.0",
    capabilities: ["mqtt", "ntp", "wifi_ap"],
    mqtt: {
      host: "192.168.50.1",
      port: 1883,
      username_file: "/etc/inas/credentials/mqtt-username",
      password_file: "/etc/inas/credentials/mqtt-password",
      keepalive_seconds: 60,
    },
    parent: {
      base_url: values.cloudOrigin,
      bearer_token_file: "/etc/inas/credentials/parent-token",
      ca_file: null,
      client_certificate_file: null,
      client_key_file: null,
      timeout_seconds: 20,
      max_response_bytes: 1048576,
      allow_insecure_http: false,
    },
    health: {
      bind_host: "192.168.50.1",
      port: 39152,
    },
  };
  const shipment = {
    schema_version: 1,
    node_id: values.nodeId,
    tenant_public_id: values.tenantPublicId,
    tenant_display_name: values.tenantDisplayName,
    label: values.label,
    hardware_profile_id: values.hardwareProfile,
    parent_credential_expires_at: values.credentialExpiresAt,
    cloud_hub_url: cloudHubUrl,
    installation_tools: [
      "smartphone",
      "USB-C power supply",
      "Ethernet cable (when required)",
    ],
    secret_file_paths: [
      "etc/inas/credentials/parent-token",
      "etc/inas/credentials/mqtt-password",
      "factory/ap-setup.txt",
      "factory/ap-wifi-qr.svg",
    ],
  };
  return new Map([
    [
      "var/lib/inas/identity.json",
      { content: `${JSON.stringify(identity, null, 2)}\n`, mode: 0o600 },
    ],
    [
      "etc/inas/edge-gateway.json",
      { content: `${JSON.stringify(config, null, 2)}\n`, mode: 0o600 },
    ],
    [
      "etc/inas/credentials/parent-token",
      { content: `${values.parentToken}\n`, mode: 0o600 },
    ],
    [
      "etc/inas/credentials/mqtt-username",
      { content: `${values.mqttUsername}\n`, mode: 0o600 },
    ],
    [
      "etc/inas/credentials/mqtt-password",
      { content: `${values.mqttPassword}\n`, mode: 0o600 },
    ],
    [
      "factory/ap-setup.txt",
      {
        content:
          `Gateway: ${values.label}\nNode ID: ${values.nodeId}\n` +
          `Device AP SSID: ${apSsid}\nDevice AP password: ${values.apPassword}\n` +
          `Cloud Hub: ${cloudHubUrl}\n`,
        mode: 0o600,
      },
    ],
    [
      "factory/ap-wifi-qr.svg",
      { content: qrSvg(apWifiPayload), mode: 0o600 },
    ],
    [
      "factory/cloud-hub-qr.svg",
      { content: qrSvg(cloudHubUrl), mode: 0o600 },
    ],
    [
      "shipment.json",
      { content: `${JSON.stringify(shipment, null, 2)}\n`, mode: 0o600 },
    ],
  ]);
}
