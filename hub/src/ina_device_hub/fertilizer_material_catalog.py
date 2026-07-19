import copy
import json
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def _load_builtin_catalog():
    catalog_path = files("ina_device_hub").joinpath("data/fertilizer_material_catalog.json")
    with catalog_path.open(encoding="utf-8") as file:
        payload = json.load(file)
    materials = payload.get("materials") if isinstance(payload, dict) else None
    if not isinstance(materials, list):
        raise ValueError("built-in fertilizer catalog must contain a materials list")
    normalized = []
    for item in materials:
        if not isinstance(item, dict) or not str(item.get("id") or "").startswith("builtin:"):
            raise ValueError("built-in fertilizer material ids must use the builtin: prefix")
        normalized.append(
            {
                **item,
                "scope": "builtin",
                "catalog_revision": int(payload.get("schema_version") or 1),
                "created_at": "",
                "updated_at": "",
            }
        )
    return normalized


def builtin_fertilizer_materials():
    return copy.deepcopy(_load_builtin_catalog())
