const MAX_JSON_DEPTH = 20;
const MAX_JSON_NODES = 10_000;
const MAX_ARRAY_ITEMS = 1_000;
const MAX_OBJECT_PROPERTIES = 200;
const MAX_KEY_LENGTH = 200;
const MAX_STRING_LENGTH = 128 * 1024;
const DANGEROUS_KEYS = new Set(["__proto__", "constructor", "prototype"]);

export class JsonSafetyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "JsonSafetyError";
  }
}

export function assertSafeJson(value: unknown, field: string): void {
  let nodes = 0;

  const visit = (current: unknown, depth: number): void => {
    nodes += 1;
    if (nodes > MAX_JSON_NODES) {
      throw new JsonSafetyError(`${field} is too complex`);
    }
    if (depth > MAX_JSON_DEPTH) {
      throw new JsonSafetyError(`${field} is nested too deeply`);
    }
    if (
      current === null ||
      typeof current === "boolean" ||
      (typeof current === "number" && Number.isFinite(current))
    ) {
      return;
    }
    if (typeof current === "string") {
      if (current.length > MAX_STRING_LENGTH) {
        throw new JsonSafetyError(`${field} contains an oversized string`);
      }
      return;
    }
    if (Array.isArray(current)) {
      if (current.length > MAX_ARRAY_ITEMS) {
        throw new JsonSafetyError(`${field} contains too many array items`);
      }
      for (const item of current) {
        visit(item, depth + 1);
      }
      return;
    }
    if (typeof current !== "object") {
      throw new JsonSafetyError(`${field} contains an unsupported value`);
    }
    const prototype = Object.getPrototypeOf(current);
    if (prototype !== Object.prototype && prototype !== null) {
      throw new JsonSafetyError(`${field} contains a non-JSON object`);
    }
    const entries = Object.entries(current as Record<string, unknown>);
    if (entries.length > MAX_OBJECT_PROPERTIES) {
      throw new JsonSafetyError(`${field} contains too many object properties`);
    }
    for (const [key, item] of entries) {
      if (
        key.length === 0 ||
        key.length > MAX_KEY_LENGTH ||
        DANGEROUS_KEYS.has(key) ||
        /[\u0000-\u001f\u007f]/.test(key)
      ) {
        throw new JsonSafetyError(`${field} contains an unsafe object key`);
      }
      visit(item, depth + 1);
    }
  };

  visit(value, 0);
}
