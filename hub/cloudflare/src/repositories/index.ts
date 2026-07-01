import { createTursoClient } from "../db";
import type { AppServices, Env } from "../types";
import { AdminUserRepository } from "./admin-users";
import { AuditLogRepository } from "./audit-logs";
import { DeviceEventRepository } from "./device-events";

export function createServices(env: Env): AppServices {
  const client = createTursoClient(env);
  return {
    deviceEvents: new DeviceEventRepository(client),
    adminUsers: new AdminUserRepository(client),
    auditLogs: new AuditLogRepository(client),
  };
}
