import assert from "node:assert/strict";

import { mergeLayouts } from "../src/layoutMerge.ts";

const base = {
  schema_version: 3,
  id: "layout-field-1",
  field_id: "field-1",
  name: "圃場",
  root_space_id: "space-root",
  spaces: [{
    id: "space-root",
    name: "圃場全体",
    space_type: "field",
    north_angle_deg: 0,
    grid: { columns: 40, rows: 28, cell_size_m: 0.5 },
    placements: [{
      id: "pot-a",
      preset: "pot",
      name: "鉢A",
      x: 1,
      y: 1,
      width: 2,
      height: 2,
      rotation: 0,
      z: 0,
      child_space_id: "",
      binding: null,
      memo: "",
    }],
  }],
  revision: 1,
  updated_at: "2026-07-15T01:00:00Z",
  updated_by: "first@example.com",
};

const localSeparate = structuredClone(base);
localSeparate.spaces[0].north_angle_deg = 45;
const serverSeparate = structuredClone(base);
serverSeparate.name = "サーバー名";
serverSeparate.revision = 2;
serverSeparate.updated_by = "other@example.com";

const separate = mergeLayouts(base, localSeparate, serverSeparate);
assert.deepEqual(separate.conflictPaths, []);
assert.equal(separate.localPreferred.name, "サーバー名");
assert.equal(separate.localPreferred.spaces[0].north_angle_deg, 45);
assert.equal(separate.localPreferred.revision, 2);

const localConflict = structuredClone(base);
localConflict.spaces[0].placements[0].name = "自分の鉢名";
const serverConflict = structuredClone(serverSeparate);
serverConflict.spaces[0].placements[0].name = "相手の鉢名";

const conflict = mergeLayouts(base, localConflict, serverConflict);
assert.equal(conflict.conflictPaths.length, 1);
assert.match(conflict.conflictPaths[0], /配置 pot-a.*名前/);
assert.equal(conflict.localPreferred.spaces[0].placements[0].name, "自分の鉢名");
assert.equal(conflict.serverPreferred.spaces[0].placements[0].name, "相手の鉢名");

process.stdout.write("layout merge tests passed\n");
