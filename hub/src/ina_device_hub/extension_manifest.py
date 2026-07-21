import json
import re

EXTENSION_API_VERSION = 1
MAX_MANIFEST_BYTES = 64 * 1024
EXTENSION_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
SEMANTIC_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:[-+][0-9A-Za-z.-]+)?$")
CONTRIBUTION_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VALUE_PATH = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*$")
BLOCK_TYPES = {"callout", "metric_grid", "process_flow"}
VALUE_SOURCES = {"config", "status", "device"}
TONES = {"leaf", "water", "sun", "neutral"}

_MANIFEST_FIELDS = {"schema_version", "id", "name", "version", "description", "compatibility", "ui"}
_COMPATIBILITY_FIELDS = {"hub_extension_api"}
_UI_FIELDS = {"device_detail"}
_DEVICE_DETAIL_FIELDS = {"device_kinds", "overview_cards", "tabs"}
_CALLOUT_FIELDS = {"id", "type", "title", "description", "tone"}
_TAB_FIELDS = {"id", "label", "title", "description", "blocks"}
_BLOCK_COMMON_FIELDS = {"type", "title"}
_PROCESS_ITEM_FIELDS = {"title", "description"}
_METRIC_ITEM_FIELDS = {"label", "value"}
_VALUE_FIELDS = {"source", "path", "unit"}


class ExtensionManifestValidationError(ValueError):
    pass


def _reject_unknown_fields(value, allowed, field, extension_id):
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ExtensionManifestValidationError(f"{field} contains unsupported fields for {extension_id}: {', '.join(unknown)}")


def _require_text(value, field, extension_id, *, max_length):
    if not isinstance(value, str) or not value.strip():
        raise ExtensionManifestValidationError(f"{field} must be non-empty for {extension_id}")
    if len(value) > max_length:
        raise ExtensionManifestValidationError(f"{field} is too long for {extension_id}")


def _validate_block(block, extension_id):
    if not isinstance(block, dict) or block.get("type") not in BLOCK_TYPES:
        raise ExtensionManifestValidationError(f"unsupported UI block for {extension_id}")
    block_type = block["type"]
    allowed = _BLOCK_COMMON_FIELDS | ({"description", "tone"} if block_type == "callout" else {"items"})
    _reject_unknown_fields(block, allowed, block_type, extension_id)
    _require_text(block.get("title"), "block.title", extension_id, max_length=120)
    if block_type == "callout":
        _require_text(block.get("description"), "callout.description", extension_id, max_length=1200)
        if block.get("tone", "leaf") not in TONES:
            raise ExtensionManifestValidationError(f"unsupported callout tone for {extension_id}")
        return
    items = block.get("items")
    if not isinstance(items, list) or not items or len(items) > 20:
        raise ExtensionManifestValidationError(f"{block_type}.items must contain 1 to 20 items for {extension_id}")
    for item in items:
        if not isinstance(item, dict):
            raise ExtensionManifestValidationError(f"{block_type} item must be an object for {extension_id}")
        if block_type == "process_flow":
            _reject_unknown_fields(item, _PROCESS_ITEM_FIELDS, "process_flow item", extension_id)
            _require_text(item.get("title"), "process_flow item.title", extension_id, max_length=100)
            _require_text(item.get("description"), "process_flow item.description", extension_id, max_length=600)
            continue
        _reject_unknown_fields(item, _METRIC_ITEM_FIELDS, "metric_grid item", extension_id)
        _require_text(item.get("label"), "metric_grid item.label", extension_id, max_length=100)
        value = item.get("value")
        if not isinstance(value, dict) or value.get("source") not in VALUE_SOURCES:
            raise ExtensionManifestValidationError(f"metric_grid item.value.source is invalid for {extension_id}")
        _reject_unknown_fields(value, _VALUE_FIELDS, "metric_grid item.value", extension_id)
        if not isinstance(value.get("path"), str) or not VALUE_PATH.fullmatch(value["path"]):
            raise ExtensionManifestValidationError(f"metric_grid item.value.path is invalid for {extension_id}")
        if "unit" in value and (not isinstance(value["unit"], str) or len(value["unit"]) > 24):
            raise ExtensionManifestValidationError(f"metric_grid item.value.unit is invalid for {extension_id}")


def _validate_device_detail(device_detail, extension_id):
    if not isinstance(device_detail, dict):
        raise ExtensionManifestValidationError(f"ui.device_detail must be an object for {extension_id}")
    _reject_unknown_fields(device_detail, _DEVICE_DETAIL_FIELDS, "ui.device_detail", extension_id)
    device_kinds = device_detail.get("device_kinds")
    if not isinstance(device_kinds, list) or not device_kinds or len(device_kinds) > 32:
        raise ExtensionManifestValidationError(f"ui.device_detail.device_kinds must contain 1 to 32 values for {extension_id}")
    if not all(isinstance(kind, str) and kind.strip() and kind == kind.upper() and len(kind) <= 16 for kind in device_kinds):
        raise ExtensionManifestValidationError(f"device kinds must be uppercase text for {extension_id}")
    if len(device_kinds) != len(set(device_kinds)):
        raise ExtensionManifestValidationError(f"device kinds must be unique for {extension_id}")

    overview_cards = device_detail.get("overview_cards") or []
    if not isinstance(overview_cards, list) or len(overview_cards) > 8:
        raise ExtensionManifestValidationError(f"overview_cards must contain at most 8 items for {extension_id}")
    seen_ids = set()
    for card in overview_cards:
        if not isinstance(card, dict) or card.get("type") != "callout":
            raise ExtensionManifestValidationError(f"overview cards must use the callout type for {extension_id}")
        _reject_unknown_fields(card, _CALLOUT_FIELDS, "overview card", extension_id)
        card_id = card.get("id")
        if not isinstance(card_id, str) or not CONTRIBUTION_ID.fullmatch(card_id) or card_id in seen_ids:
            raise ExtensionManifestValidationError(f"overview card IDs must be unique kebab-case for {extension_id}")
        seen_ids.add(card_id)
        _validate_block({key: value for key, value in card.items() if key != "id"}, extension_id)

    tabs = device_detail.get("tabs") or []
    if not isinstance(tabs, list) or len(tabs) > 4:
        raise ExtensionManifestValidationError(f"tabs must contain at most 4 items for {extension_id}")
    seen_ids.clear()
    for tab in tabs:
        if not isinstance(tab, dict):
            raise ExtensionManifestValidationError(f"tabs must contain objects for {extension_id}")
        _reject_unknown_fields(tab, _TAB_FIELDS, "tab", extension_id)
        tab_id = tab.get("id")
        if not isinstance(tab_id, str) or not CONTRIBUTION_ID.fullmatch(tab_id) or tab_id in seen_ids:
            raise ExtensionManifestValidationError(f"tab IDs must be unique kebab-case for {extension_id}")
        seen_ids.add(tab_id)
        _require_text(tab.get("label"), "tab.label", extension_id, max_length=32)
        _require_text(tab.get("title"), "tab.title", extension_id, max_length=120)
        _require_text(tab.get("description"), "tab.description", extension_id, max_length=800)
        blocks = tab.get("blocks")
        if not isinstance(blocks, list) or not blocks or len(blocks) > 12:
            raise ExtensionManifestValidationError(f"tab.blocks must contain 1 to 12 items for {extension_id}")
        for block in blocks:
            _validate_block(block, extension_id)
    if not overview_cards and not tabs:
        raise ExtensionManifestValidationError(f"ui.device_detail must contain a visible contribution for {extension_id}")


def validate_extension_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ExtensionManifestValidationError("Extension manifest must be an object")
    if len(json.dumps(manifest, ensure_ascii=False).encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise ExtensionManifestValidationError("Extension manifest is too large")
    extension_id = str(manifest.get("id") or "").strip()
    if manifest.get("schema_version") != 1 or not EXTENSION_ID.fullmatch(extension_id) or extension_id.count(".") < 2 or len(extension_id) > 128:
        raise ExtensionManifestValidationError("invalid Extension header")
    _reject_unknown_fields(manifest, _MANIFEST_FIELDS, "manifest", extension_id)
    _require_text(manifest.get("name"), "name", extension_id, max_length=100)
    _require_text(manifest.get("version"), "version", extension_id, max_length=64)
    if not SEMANTIC_VERSION.fullmatch(manifest["version"]):
        raise ExtensionManifestValidationError(f"version must use semantic versioning for {extension_id}")
    _require_text(manifest.get("description"), "description", extension_id, max_length=1200)
    compatibility = manifest.get("compatibility")
    if not isinstance(compatibility, dict):
        raise ExtensionManifestValidationError(f"compatibility must be an object for {extension_id}")
    _reject_unknown_fields(compatibility, _COMPATIBILITY_FIELDS, "compatibility", extension_id)
    if compatibility.get("hub_extension_api") != EXTENSION_API_VERSION:
        raise ExtensionManifestValidationError(f"unsupported Hub Extension API for {extension_id}")
    ui = manifest.get("ui") or {}
    if not isinstance(ui, dict):
        raise ExtensionManifestValidationError(f"ui must be an object for {extension_id}")
    _reject_unknown_fields(ui, _UI_FIELDS, "ui", extension_id)
    if "device_detail" in ui:
        _validate_device_detail(ui["device_detail"], extension_id)
    if not ui:
        raise ExtensionManifestValidationError(f"Extension must provide at least one supported contribution for {extension_id}")
    return manifest
