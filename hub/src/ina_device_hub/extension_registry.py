import copy
import json
import re
from functools import lru_cache
from pathlib import Path

from ina_device_hub.device_definition_registry import value_at_path
from ina_device_hub.extension_manifest import ExtensionManifestValidationError, validate_extension_manifest
from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting

_REGISTRY_PATH = Path(__file__).with_name("extensions") / "generated" / "registry.json"
_DOM_TOKEN = re.compile(r"[^a-z0-9-]+")


@lru_cache(maxsize=1)
def _bundled_registry():
    value = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or value.get("extension_api_version") != 1 or not isinstance(value.get("extensions"), dict):
        raise RuntimeError("generated Hub Extension registry is invalid")
    return value["extensions"]


def _installed_extensions():
    root = Path(setting().get_work_dir()) / "extensions" / "installed"
    installed = {}
    if not root.exists():
        return installed
    for manifest_path in sorted(root.glob("*/*/extension.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            validate_extension_manifest(manifest)
            extension_id = manifest["id"]
            if extension_id in installed or extension_id in _bundled_registry():
                logger.warning("Ignoring duplicate installed Extension: %s", extension_id)
                continue
            installed[extension_id] = {**manifest, "source": f"installed:{manifest_path.parent.relative_to(root)}"}
        except (OSError, json.JSONDecodeError, ExtensionManifestValidationError):
            logger.exception("Ignoring invalid installed Extension: %s", manifest_path)
    return installed


@lru_cache(maxsize=1)
def _registry():
    return {**_bundled_registry(), **_installed_extensions()}


def reload_extension_registry():
    _registry.cache_clear()


def list_extensions():
    return [copy.deepcopy(value) for _, value in sorted(_registry().items())]


def _format_value(value, unit=""):
    if value is None or value == "":
        return "未設定"
    if isinstance(value, bool):
        text = "有効" if value else "無効"
    elif isinstance(value, float):
        text = f"{value:g}"
    else:
        text = str(value)
    return f"{text} {unit}".strip()


def _resolve_block(block, sources):
    resolved = copy.deepcopy(block)
    if resolved.get("type") != "metric_grid":
        return resolved
    for item in resolved.get("items") or []:
        reference = item.pop("value", {})
        source = sources.get(reference.get("source")) or {}
        item["display_value"] = _format_value(value_at_path(source, reference.get("path")), reference.get("unit") or "")
    return resolved


def build_device_detail_extensions(device_kind, *, device=None, status=None, config=None):
    kind = str(device_kind or "").strip().upper()
    sources = {"device": device or {}, "status": status or {}, "config": config or {}}
    contributions = []
    for extension in list_extensions():
        detail = (extension.get("ui") or {}).get("device_detail") or {}
        if kind not in detail.get("device_kinds", []):
            continue
        extension_dom_id = _DOM_TOKEN.sub("-", extension["id"].lower()).strip("-")
        overview_cards = [_resolve_block(card, sources) for card in detail.get("overview_cards") or []]
        tabs = []
        for tab in detail.get("tabs") or []:
            resolved_tab = copy.deepcopy(tab)
            resolved_tab["dom_id"] = f"extension-{extension_dom_id}-{tab['id']}"
            resolved_tab["key"] = f"ext-{extension_dom_id}-{tab['id']}"
            resolved_tab["blocks"] = [_resolve_block(block, sources) for block in tab.get("blocks") or []]
            tabs.append(resolved_tab)
        contributions.append(
            {
                "id": extension["id"],
                "name": extension["name"],
                "version": extension["version"],
                "description": extension["description"],
                "overview_cards": overview_cards,
                "tabs": tabs,
            }
        )
    return contributions
