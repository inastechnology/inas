import copy
import json
import os
from datetime import UTC, datetime

from ina_device_hub.json_repository_io import atomic_write_json, repository_file_lock
from ina_device_hub.setting import setting

LAYOUT_SCHEMA_VERSION = 3
MAX_LAYOUT_SPACES = 50
MAX_SPACE_PLACEMENTS = 500
VALID_SPACE_TYPES = {"field", "open_field", "greenhouse", "indoor", "hydroponic", "shade"}
VALID_PLACEMENT_PRESETS = {
    "greenhouse",
    "open_field",
    "shade_area",
    "ridge",
    "tree",
    "pot",
    "hydroponic_bed",
    "watering_device",
    "sensor",
    "camera",
    "irrigation_line",
    "tank",
    "grow_light",
    "mister",
    "fan",
    "hvac",
}
VALID_BINDING_RESOURCE_TYPES = {"device", "mosfet_switch", "sensor", "camera"}
VALID_TARGET_PLACEMENT_PRESETS = {
    "greenhouse",
    "open_field",
    "shade_area",
    "ridge",
    "tree",
    "pot",
    "hydroponic_bed",
}


class FieldLayoutValidationError(ValueError):
    pass


class FieldLayoutConflictError(ValueError):
    def __init__(self, current):
        super().__init__("layout was updated by another client")
        self.current = current


class FieldLayoutRepository:
    layout_repo_path = os.path.join(setting().get_work_dir(), ".field_layouts.json")

    def __init__(self):
        self.layouts = {}
        with repository_file_lock(self.layout_repo_path):
            self.load()

    def load(self):
        if not os.path.exists(self.layout_repo_path):
            atomic_write_json(self.layout_repo_path, {})
        try:
            with open(self.layout_repo_path, encoding="utf-8") as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        self.layouts = {field_id: value for field_id, value in data.items() if isinstance(value, dict)}

    def save(self):
        atomic_write_json(self.layout_repo_path, self.layouts)

    def get(self, field_id: str, field_name: str = ""):
        with repository_file_lock(self.layout_repo_path):
            self.load()
            record = self.layouts.get(field_id)
            if record is None:
                return _new_layout(field_id, field_name)
            return copy.deepcopy(_normalize_layout(field_id, record, field_name=field_name))

    def upsert(self, field_id: str, data: dict, field_name: str = "", updated_by: str = ""):
        if not isinstance(data, dict):
            raise FieldLayoutValidationError("layout data must be an object")

        with repository_file_lock(self.layout_repo_path):
            self.load()
            current = self.layouts.get(field_id)
            current_revision = _clean_int(current.get("revision"), 0) if current else 0
            supplied_revision = _clean_int(data.get("revision"), 0)
            if supplied_revision != current_revision:
                current_layout = _normalize_layout(field_id, current, field_name=field_name) if current else _new_layout(field_id, field_name)
                raise FieldLayoutConflictError(copy.deepcopy(current_layout))

            normalized = _normalize_layout(field_id, data, field_name=field_name)
            normalized["revision"] = current_revision + 1
            normalized["updated_at"] = _utc_now()
            normalized["updated_by"] = _clean_string(updated_by, "unknown")
            self.layouts[field_id] = normalized
            self.save()
            return copy.deepcopy(normalized)


def _new_layout(field_id: str, field_name: str):
    root_space_id = "space-root"
    return {
        "schema_version": LAYOUT_SCHEMA_VERSION,
        "id": f"layout-{field_id}",
        "field_id": field_id,
        "name": field_name or "設置ビュー",
        "root_space_id": root_space_id,
        "spaces": [
            {
                "id": root_space_id,
                "name": field_name or "圃場全体",
                "space_type": "field",
                "north_angle_deg": 0,
                "grid": {"columns": 40, "rows": 28, "cell_size_m": 0.5},
                "placements": [],
            }
        ],
        "revision": 0,
        "updated_at": "",
        "updated_by": "",
    }


def _normalize_layout(field_id: str, value: dict, field_name: str = ""):
    spaces_value = value.get("spaces")
    if not isinstance(spaces_value, list) or not spaces_value:
        raise FieldLayoutValidationError("spaces must be a non-empty array")
    if len(spaces_value) > MAX_LAYOUT_SPACES:
        raise FieldLayoutValidationError(f"spaces must contain {MAX_LAYOUT_SPACES} entries or less")

    spaces = []
    space_ids = set()
    for index, space_value in enumerate(spaces_value):
        space = _normalize_space(space_value, index)
        if space["id"] in space_ids:
            raise FieldLayoutValidationError(f"spaces[{index}].id must be unique")
        spaces.append(space)
        space_ids.add(space["id"])

    root_space_id = _clean_string(value.get("root_space_id"), "space-root")
    if root_space_id not in space_ids:
        raise FieldLayoutValidationError("root_space_id must reference an existing space")

    child_space_ids = set()
    placement_ids = set()
    bound_device_ids = set()
    for space_index, space in enumerate(spaces):
        for placement_index, placement in enumerate(space["placements"]):
            if placement["id"] in placement_ids:
                raise FieldLayoutValidationError("placement ids must be unique across all spaces")
            placement_ids.add(placement["id"])
            binding = placement.get("binding") or {}
            device_id = binding.get("device_id")
            if device_id in bound_device_ids:
                raise FieldLayoutValidationError("a device can only be assigned to one placement")
            if device_id:
                bound_device_ids.add(device_id)
            child_space_id = placement.get("child_space_id")
            if not child_space_id:
                continue
            if child_space_id not in space_ids:
                raise FieldLayoutValidationError(f"spaces[{space_index}].placements[{placement_index}].child_space_id must reference an existing space")
            if child_space_id == space["id"]:
                raise FieldLayoutValidationError("a placement cannot reference its own space")
            if child_space_id in child_space_ids:
                raise FieldLayoutValidationError("a child space can only be assigned to one placement")
            child_space_ids.add(child_space_id)

    placements_by_id = {placement["id"]: placement for space in spaces for placement in space["placements"]}
    for placement in placements_by_id.values():
        for target_id in (placement.get("binding") or {}).get("target_placement_ids", []):
            target = placements_by_id.get(target_id)
            if target is None:
                raise FieldLayoutValidationError("binding target_placement_ids must reference an existing placement")
            if target_id == placement["id"]:
                raise FieldLayoutValidationError("a device placement cannot target itself")
            if target["preset"] not in VALID_TARGET_PLACEMENT_PRESETS:
                raise FieldLayoutValidationError("a device target must be a space or growing-medium placement")

    return {
        "schema_version": LAYOUT_SCHEMA_VERSION,
        "id": f"layout-{field_id}",
        "field_id": field_id,
        "name": _clean_string(value.get("name"), field_name or "設置ビュー"),
        "root_space_id": root_space_id,
        "spaces": spaces,
        "revision": _clean_int(value.get("revision"), 0),
        "updated_at": _clean_string(value.get("updated_at")),
        "updated_by": _clean_string(value.get("updated_by")),
    }


def _normalize_space(value, index: int):
    if not isinstance(value, dict):
        raise FieldLayoutValidationError(f"spaces[{index}] must be an object")
    space_id = _required_string(value.get("id"), f"spaces[{index}].id", 80)
    name = _required_string(value.get("name"), f"spaces[{index}].name", 120)
    space_type = _clean_string(value.get("space_type"), "field")
    if space_type not in VALID_SPACE_TYPES:
        raise FieldLayoutValidationError(f"spaces[{index}].space_type is unsupported")

    grid_value = value.get("grid") if isinstance(value.get("grid"), dict) else {}
    columns = _bounded_int(grid_value.get("columns"), 40, 8, 200, f"spaces[{index}].grid.columns")
    rows = _bounded_int(grid_value.get("rows"), 28, 8, 200, f"spaces[{index}].grid.rows")
    cell_size_m = _bounded_float(grid_value.get("cell_size_m"), 0.5, 0.01, 100.0, f"spaces[{index}].grid.cell_size_m")

    placements_value = value.get("placements")
    if placements_value is None:
        placements_value = []
    if not isinstance(placements_value, list):
        raise FieldLayoutValidationError(f"spaces[{index}].placements must be an array")
    if len(placements_value) > MAX_SPACE_PLACEMENTS:
        raise FieldLayoutValidationError(f"spaces[{index}].placements must contain {MAX_SPACE_PLACEMENTS} entries or less")

    placements = []
    placement_ids = set()
    for placement_index, placement_value in enumerate(placements_value):
        placement = _normalize_placement(placement_value, index, placement_index, columns, rows)
        if placement["id"] in placement_ids:
            raise FieldLayoutValidationError(f"spaces[{index}].placements[{placement_index}].id must be unique")
        placement_ids.add(placement["id"])
        placements.append(placement)

    return {
        "id": space_id,
        "name": name,
        "space_type": space_type,
        "north_angle_deg": _bounded_int(value.get("north_angle_deg"), 0, 0, 359, f"spaces[{index}].north_angle_deg"),
        "grid": {"columns": columns, "rows": rows, "cell_size_m": cell_size_m},
        "placements": placements,
    }


def _normalize_placement(value, space_index: int, placement_index: int, columns: int, rows: int):
    path = f"spaces[{space_index}].placements[{placement_index}]"
    if not isinstance(value, dict):
        raise FieldLayoutValidationError(f"{path} must be an object")
    placement_id = _required_string(value.get("id"), f"{path}.id", 80)
    preset = _clean_string(value.get("preset"))
    if preset not in VALID_PLACEMENT_PRESETS:
        raise FieldLayoutValidationError(f"{path}.preset is unsupported")
    name = _required_string(value.get("name"), f"{path}.name", 120)
    x = _bounded_int(value.get("x"), 0, 0, columns - 1, f"{path}.x")
    y = _bounded_int(value.get("y"), 0, 0, rows - 1, f"{path}.y")
    width = _bounded_int(value.get("width"), 1, 1, columns, f"{path}.width")
    height = _bounded_int(value.get("height"), 1, 1, rows, f"{path}.height")
    if x + width > columns or y + height > rows:
        raise FieldLayoutValidationError(f"{path} must fit inside its space grid")
    rotation = _clean_int(value.get("rotation"), 0)
    if rotation not in {0, 90, 180, 270}:
        raise FieldLayoutValidationError(f"{path}.rotation must be 0, 90, 180, or 270")

    return {
        "id": placement_id,
        "preset": preset,
        "name": name,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "rotation": rotation,
        "z": _bounded_int(value.get("z"), placement_index, 0, MAX_SPACE_PLACEMENTS, f"{path}.z"),
        "child_space_id": _clean_string(value.get("child_space_id")),
        "binding": _normalize_binding(value.get("binding"), path),
        "memo": _clean_string(value.get("memo"))[:500],
    }


def _normalize_binding(value, path: str):
    if value in (None, ""):
        return None
    if not isinstance(value, dict):
        raise FieldLayoutValidationError(f"{path}.binding must be an object or null")
    device_id = _clean_string(value.get("device_id"))
    if not device_id:
        return None
    resource_type = _clean_string(value.get("resource_type"), "device")
    if resource_type not in VALID_BINDING_RESOURCE_TYPES:
        raise FieldLayoutValidationError(f"{path}.binding.resource_type is unsupported")
    return {
        "device_id": device_id[:120],
        "resource_type": resource_type,
        "resource_id": _clean_string(value.get("resource_id"))[:120],
        "target_placement_ids": _clean_string_list(value.get("target_placement_ids"), limit=100, item_length=80),
    }


def _clean_string_list(value, *, limit: int, item_length: int):
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        text = _clean_string(item)[:item_length]
        if text and text not in items:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def _utc_now():
    return datetime.now(UTC).isoformat()


def _clean_string(value, default=""):
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _required_string(value, path: str, max_length: int):
    text = _clean_string(value)
    if not text:
        raise FieldLayoutValidationError(f"{path} is required")
    if len(text) > max_length:
        raise FieldLayoutValidationError(f"{path} must be {max_length} characters or less")
    return text


def _clean_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bounded_int(value, default: int, minimum: int, maximum: int, path: str):
    try:
        number = int(value) if value not in (None, "") else default
    except (TypeError, ValueError) as exc:
        raise FieldLayoutValidationError(f"{path} must be an integer") from exc
    if number < minimum or number > maximum:
        raise FieldLayoutValidationError(f"{path} must be between {minimum} and {maximum}")
    return number


def _bounded_float(value, default: float, minimum: float, maximum: float, path: str):
    try:
        number = float(value) if value not in (None, "") else default
    except (TypeError, ValueError) as exc:
        raise FieldLayoutValidationError(f"{path} must be a number") from exc
    if number < minimum or number > maximum:
        raise FieldLayoutValidationError(f"{path} must be between {minimum} and {maximum}")
    return number


__instance = None


def field_layout_repository():
    global __instance  # noqa: PLW0603
    if not __instance:
        __instance = FieldLayoutRepository()
    return __instance
