import type { Role, SqlClient } from "../types";

const ROLES = new Set<Role>(["reader", "operator", "admin"]);

export class AdminUserRepository {
  constructor(private readonly client: SqlClient) {}

  async roleForEmail(email: string): Promise<Role | null> {
    const result = await this.client.execute({
      sql: "SELECT role FROM admin_users WHERE lower(email) = lower(?) LIMIT 1",
      args: [email],
    });
    const role = result.rows[0]?.role;
    return typeof role === "string" && ROLES.has(role as Role) ? (role as Role) : null;
  }
}
