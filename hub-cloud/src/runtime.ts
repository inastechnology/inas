import { decryptTenantCredential } from "./crypto";
import { createDirectoryClient, createTenantClient, requiredEnv } from "./database";
import { DashboardRepository } from "./repositories/dashboard";
import { DeviceEventRepository } from "./repositories/device-events";
import { DirectoryRepository } from "./repositories/directory";
import { SyncRepository } from "./repositories/sync";
import type { CloudRuntime, Env, TenantRecord, TenantServices } from "./types";

export function createCloudRuntime(env: Env): CloudRuntime {
  const directory = new DirectoryRepository(createDirectoryClient(env));
  const masterKey = requiredEnv(env.TENANT_CREDENTIAL_MASTER_KEY, "TENANT_CREDENTIAL_MASTER_KEY");
  return {
    directory,
    async tenantServices(tenant: TenantRecord): Promise<TenantServices> {
      if (tenant.credentialKeyVersion !== 2) {
        throw new Error(`unsupported tenant credential key version: ${tenant.credentialKeyVersion}`);
      }
      const authToken = await decryptTenantCredential(
        masterKey,
        {
          tenantId: tenant.id,
          databaseName: tenant.databaseName,
          databaseUrl: tenant.databaseUrl,
        },
        tenant.encryptedAuthToken,
      );
      const client = createTenantClient(tenant.databaseUrl, authToken);
      const events = new DeviceEventRepository(client);
      const dashboard = new DashboardRepository(client);
      const sync = new SyncRepository(client);
      return {
        events: {
          list: (filters) => events.list(filters),
          createManagementEvent: (input) => events.createManagementEvent(input),
        },
        dashboard: {
          summary: () => dashboard.summary(),
        },
        sync: {
          exchange: (node, request) => sync.exchange(node, request),
        },
      };
    },
  };
}
