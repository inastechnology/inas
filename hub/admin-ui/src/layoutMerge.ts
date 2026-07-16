import type { FieldLayout } from "./types";

interface MergeResult {
  localPreferred: FieldLayout;
  serverPreferred: FieldLayout;
  conflictPaths: string[];
}

const MISSING = Symbol("missing");
type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
type MergeValue = JsonValue | typeof MISSING;

export function mergeLayouts(base: FieldLayout, local: FieldLayout, server: FieldLayout): MergeResult {
  const localResult = mergeValue(base as unknown as JsonValue, local as unknown as JsonValue, server as unknown as JsonValue, "layout", "local");
  const serverResult = mergeValue(base as unknown as JsonValue, local as unknown as JsonValue, server as unknown as JsonValue, "layout", "server");
  return {
    localPreferred: finalize(localResult.value, server),
    serverPreferred: finalize(serverResult.value, server),
    conflictPaths: Array.from(new Set(localResult.conflicts)),
  };
}

function finalize(value: MergeValue, server: FieldLayout): FieldLayout {
  const merged = (value === MISSING ? structuredClone(server) : value) as unknown as FieldLayout;
  merged.revision = server.revision;
  merged.updated_at = server.updated_at;
  merged.updated_by = server.updated_by;
  return merged;
}

function mergeValue(
  base: MergeValue,
  local: MergeValue,
  server: MergeValue,
  path: string,
  preference: "local" | "server",
): { value: MergeValue; conflicts: string[] } {
  if (same(local, server)) return { value: cloneValue(local), conflicts: [] };
  if (same(local, base)) return { value: cloneValue(server), conflicts: [] };
  if (same(server, base)) return { value: cloneValue(local), conflicts: [] };

  if (isObject(local) && isObject(server) && (isObject(base) || base === MISSING)) {
    const baseObject = isObject(base) ? base : {};
    const keys = new Set([...Object.keys(baseObject), ...Object.keys(local), ...Object.keys(server)]);
    const value: Record<string, JsonValue> = {};
    const conflicts: string[] = [];
    keys.forEach((key) => {
      const merged = mergeValue(
        key in baseObject ? baseObject[key] : MISSING,
        key in local ? local[key] : MISSING,
        key in server ? server[key] : MISSING,
        `${path}.${key}`,
        preference,
      );
      if (merged.value !== MISSING) value[key] = merged.value;
      conflicts.push(...merged.conflicts);
    });
    return { value, conflicts };
  }

  if (isKeyedArray(local) && isKeyedArray(server) && (isKeyedArray(base) || base === MISSING)) {
    return mergeKeyedArray(base === MISSING ? [] : base, local, server, path, preference);
  }

  return {
    value: cloneValue(preference === "local" ? local : server),
    conflicts: [friendlyPath(path)],
  };
}

function mergeKeyedArray(
  base: JsonValue[],
  local: JsonValue[],
  server: JsonValue[],
  path: string,
  preference: "local" | "server",
): { value: JsonValue[]; conflicts: string[] } {
  const byId = (items: JsonValue[]) => new Map(items.map((item) => [(item as { id: string }).id, item]));
  const baseById = byId(base);
  const localById = byId(local);
  const serverById = byId(server);
  const orderedIds = Array.from(new Set([
    ...server.map((item) => (item as { id: string }).id),
    ...local.map((item) => (item as { id: string }).id),
    ...base.map((item) => (item as { id: string }).id),
  ]));
  const value: JsonValue[] = [];
  const conflicts: string[] = [];
  orderedIds.forEach((id) => {
    const merged = mergeValue(
      baseById.get(id) ?? MISSING,
      localById.get(id) ?? MISSING,
      serverById.get(id) ?? MISSING,
      `${path}[${id}]`,
      preference,
    );
    if (merged.value !== MISSING) value.push(merged.value);
    conflicts.push(...merged.conflicts);
  });
  return { value, conflicts };
}

function isObject(value: MergeValue): value is { [key: string]: JsonValue } {
  return value !== MISSING && value !== null && typeof value === "object" && !Array.isArray(value);
}

function isKeyedArray(value: MergeValue): value is JsonValue[] {
  return Array.isArray(value) && value.every((item) => isObject(item) && typeof item.id === "string");
}

function same(left: MergeValue, right: MergeValue): boolean {
  if (left === MISSING || right === MISSING) return left === right;
  return JSON.stringify(left) === JSON.stringify(right);
}

function cloneValue(value: MergeValue): MergeValue {
  return value === MISSING ? MISSING : structuredClone(value);
}

function friendlyPath(path: string): string {
  return path
    .replace(/^layout\./, "")
    .replace(/spaces\[([^\]]+)]/, "空間 $1")
    .replace(/\.placements\[([^\]]+)]/, " / 配置 $1")
    .replace(/\.name$/, " / 名前")
    .replace(/\.north_angle_deg$/, " / 北の向き")
    .replace(/\.grid\./, " / グリッド ")
    .replace(/\.binding\./, " / 接続 ");
}
