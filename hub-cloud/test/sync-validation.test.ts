import { describe, expect, it } from "vitest";

import { validateSyncRequest } from "../src/sync-validation";
import { EDGE_NODE_ID, OTHER_EDGE_NODE_ID, node, syncRequest } from "./helpers";

describe("Sync request validation", () => {
  it("accepts the registered node's strict Sync v1 document", () => {
    expect(validateSyncRequest(syncRequest(), EDGE_NODE_ID, node()).node_id).toBe(EDGE_NODE_ID);
  });

  it.each(["tenant_id", "database_url", "turso_auth_token"])("rejects caller-selected routing field %s", (key) => {
    expect(() =>
      validateSyncRequest({ ...syncRequest(), [key]: "attacker-selected" }, EDGE_NODE_ID, node()),
    ).toThrow(`${key} is not allowed`);
  });

  it("rejects origins and path IDs outside the authenticated node", () => {
    const request = syncRequest({
      events: [{ ...syncRequest().events[0], origin_node_id: OTHER_EDGE_NODE_ID }],
    });
    expect(() => validateSyncRequest(request, EDGE_NODE_ID, node())).toThrow(
      "outside the authenticated node",
    );
    expect(() => validateSyncRequest(syncRequest(), OTHER_EDGE_NODE_ID, node())).toThrow(
      "does not match authenticated path",
    );
  });

  it("rejects duplicate sequence identities before persistence", () => {
    const first = syncRequest().events[0];
    const request = syncRequest({
      events: [
        first,
        {
          ...first,
          event_id: "77777777-7777-4777-8777-777777777777",
        },
      ],
    });
    expect(() => validateSyncRequest(request, EDGE_NODE_ID, node())).toThrow(
      "event origin/sequence contains duplicates",
    );
  });

  it("rejects Local Hub origins at the Cloud Hub boundary", () => {
    const localNodeId = "INALH-aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    expect(() =>
      validateSyncRequest(
        {
          ...syncRequest(),
          node_id: localNodeId,
          node_type: "local_hub",
          events: [],
        },
        localNodeId,
        node({ nodeId: localNodeId, nodeType: "local_hub" }),
      ),
    ).toThrow();
  });
});
