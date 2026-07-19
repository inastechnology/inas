import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from urllib import error, request
from urllib.parse import urlparse

from ina_device_hub.general_log import logger
from ina_device_hub.json_repository_io import atomic_write_json, repository_file_lock
from ina_device_hub.setting import setting

PREFECTURE_OFFICIAL_DOMAINS = (
    "pref.hokkaido.lg.jp",
    "pref.aomori.lg.jp",
    "pref.iwate.jp",
    "pref.miyagi.jp",
    "pref.akita.lg.jp",
    "pref.yamagata.jp",
    "pref.fukushima.lg.jp",
    "pref.ibaraki.jp",
    "pref.tochigi.lg.jp",
    "pref.gunma.jp",
    "pref.saitama.lg.jp",
    "pref.chiba.lg.jp",
    "metro.tokyo.lg.jp",
    "pref.kanagawa.jp",
    "pref.niigata.lg.jp",
    "pref.toyama.jp",
    "pref.ishikawa.lg.jp",
    "pref.fukui.lg.jp",
    "pref.yamanashi.jp",
    "pref.nagano.lg.jp",
    "pref.gifu.lg.jp",
    "pref.shizuoka.jp",
    "pref.aichi.jp",
    "pref.mie.lg.jp",
    "pref.shiga.lg.jp",
    "pref.kyoto.jp",
    "pref.osaka.lg.jp",
    "pref.hyogo.lg.jp",
    "pref.nara.jp",
    "pref.wakayama.lg.jp",
    "pref.tottori.lg.jp",
    "pref.shimane.lg.jp",
    "pref.okayama.jp",
    "pref.hiroshima.lg.jp",
    "pref.yamaguchi.lg.jp",
    "pref.tokushima.lg.jp",
    "pref.kagawa.lg.jp",
    "pref.ehime.jp",
    "pref.kochi.lg.jp",
    "pref.fukuoka.lg.jp",
    "pref.saga.lg.jp",
    "pref.nagasaki.jp",
    "pref.kumamoto.jp",
    "pref.oita.jp",
    "pref.miyazaki.lg.jp",
    "pref.kagoshima.jp",
    "pref.okinawa.jp",
)
TRUSTED_CROP_KNOWLEDGE_DOMAINS = ("go.jp", "lg.jp", "naro.go.jp", "maff.go.jp", *PREFECTURE_OFFICIAL_DOMAINS)
MAX_CACHE_ENTRIES = 200
MAX_SOURCES = 8
MAX_SUMMARY_ITEMS = 8


class CropKnowledgeProvider:
    def __init__(self, *, ai_settings=None, cache_path=None, http_post=None, now=None):
        self._dynamic_settings = ai_settings is None
        self.ai_settings = ai_settings if ai_settings is not None else (setting().get("ai") or {})
        self.cache_path = cache_path or os.path.join(setting().get_work_dir(), ".crop_knowledge_cache.json")
        self.http_post = http_post or self._http_post
        self.now = now or (lambda: datetime.now(UTC))

    def get(self, context: dict, *, force_refresh: bool = False):
        if self._dynamic_settings:
            self.ai_settings = setting().get("ai") or {}
        cache_key = self._cache_key(context)
        base_result = {
            "status": "disabled",
            "provider": "openai_web_search",
            "cache_key": cache_key,
            "cache_hit": False,
            "summary": [],
            "assumptions": [],
            "sources": [],
            "fetched_at": "",
        }
        if not self.ai_settings.get("plant_calendar_web_knowledge_enabled", True):
            return base_result
        cached = self._read_cached(cache_key)
        if cached is not None and not force_refresh:
            return {**cached, "cache_hit": True}
        if self.ai_settings.get("enabled", True) is False or not self.ai_settings.get("text_analyze_api_key"):
            return {**base_result, "status": "ai_not_configured"}
        base_url = str(self.ai_settings.get("text_analyze_base_url") or "https://api.openai.com/v1").rstrip("/")
        if not _is_official_openai_base_url(base_url):
            return {**base_result, "status": "unsupported_provider"}
        model = str(self.ai_settings.get("text_analyze_model") or "").strip()
        if not model:
            return {**base_result, "status": "ai_not_configured"}

        fetched_at = self.now().isoformat()
        try:
            payload = {
                "model": model,
                "tools": [
                    {
                        "type": "web_search",
                        "filters": {"allowed_domains": list(TRUSTED_CROP_KNOWLEDGE_DOMAINS)},
                    }
                ],
                "tool_choice": "required",
                "include": ["web_search_call.action.sources"],
                "max_output_tokens": 1800,
                "input": _search_prompt(context),
            }
            response = self.http_post(
                f"{base_url}/responses",
                payload,
                str(self.ai_settings.get("text_analyze_api_key") or ""),
            )
            parsed = _parse_response(response, context=context, fetched_at=fetched_at)
            status = "available" if parsed["sources"] else "not_found"
            result = {
                **base_result,
                **parsed,
                "status": status,
                "cache_hit": False,
                "fetched_at": fetched_at,
            }
            self._write_cached(cache_key, result)
            return result
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError, error.URLError, TimeoutError):
            logger.exception("Crop knowledge web search failed; continuing without refreshed evidence")
            if cached is not None:
                return {**cached, "cache_hit": True, "refresh_failed": True}
            return {**base_result, "status": "error", "fetched_at": fetched_at}

    def _cache_key(self, context: dict):
        planting = context.get("planting") if isinstance(context.get("planting"), dict) else {}
        conditions = planting.get("conditions") if isinstance(planting.get("conditions"), dict) else {}
        field = context.get("field") if isinstance(context.get("field"), dict) else {}
        location = field.get("location") if isinstance(field.get("location"), dict) else {}
        placement = context.get("placement") if isinstance(context.get("placement"), dict) else {}
        key_input = {
            "crop_name": planting.get("crop_name") or "",
            "cultivar": planting.get("cultivar") or "",
            "crop_category": planting.get("crop_category") or "",
            "tree_age_years": planting.get("tree_age_years"),
            "cultivation_method": planting.get("cultivation_method") or "",
            "soil_or_substrate": conditions.get("soil_or_substrate") or "",
            "environment": conditions.get("environment") or placement.get("space_type") or "",
            "prefecture": location.get("prefecture") or conditions.get("region") or "",
        }
        serialized = json.dumps(key_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _read_cached(self, cache_key: str):
        cache = self._load_cache()
        entry = cache.get("entries", {}).get(cache_key)
        if not isinstance(entry, dict) or not isinstance(entry.get("result"), dict):
            return None
        try:
            fetched_at = datetime.fromisoformat(str(entry.get("fetched_at") or ""))
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=UTC)
        except ValueError:
            return None
        cache_days = _bounded_cache_days(self.ai_settings.get("plant_calendar_web_knowledge_cache_days"))
        if self.now() - fetched_at > timedelta(days=cache_days):
            return None
        return entry["result"]

    def _write_cached(self, cache_key: str, result: dict):
        with repository_file_lock(self.cache_path):
            cache = self._load_cache_unlocked()
            entries = cache.setdefault("entries", {})
            entries[cache_key] = {"fetched_at": result.get("fetched_at") or self.now().isoformat(), "result": result}
            if len(entries) > MAX_CACHE_ENTRIES:
                ordered = sorted(entries.items(), key=lambda item: str(item[1].get("fetched_at") or ""), reverse=True)
                cache["entries"] = dict(ordered[:MAX_CACHE_ENTRIES])
            atomic_write_json(self.cache_path, cache)

    def _load_cache(self):
        with repository_file_lock(self.cache_path):
            return self._load_cache_unlocked()

    def _load_cache_unlocked(self):
        try:
            with open(self.cache_path, encoding="utf-8") as file:
                value = json.load(file)
            if isinstance(value, dict) and isinstance(value.get("entries"), dict):
                return {"schema_version": 1, "entries": value["entries"]}
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return {"schema_version": 1, "entries": {}}

    @staticmethod
    def _http_post(url: str, payload: dict, api_key: str):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "INA-Device-Hub/plant-knowledge",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"crop knowledge search failed with HTTP {exc.code}: {detail}") from exc


def _search_prompt(context: dict):
    planting = context.get("planting") if isinstance(context.get("planting"), dict) else {}
    conditions = planting.get("conditions") if isinstance(planting.get("conditions"), dict) else {}
    field = context.get("field") if isinstance(context.get("field"), dict) else {}
    location = field.get("location") if isinstance(field.get("location"), dict) else {}
    planning = context.get("planning") if isinstance(context.get("planning"), dict) else {}
    facts = {
        "crop_name": planting.get("crop_name") or "",
        "cultivar": planting.get("cultivar") or "",
        "crop_category": planting.get("crop_category") or "",
        "tree_age_years": planting.get("tree_age_years"),
        "cultivation_method": planting.get("cultivation_method") or "",
        "planted_on": planting.get("planted_on") or "",
        "soil_or_substrate": conditions.get("soil_or_substrate") or "",
        "environment": conditions.get("environment") or "",
        "sunlight": conditions.get("sunlight") or "",
        "prefecture": location.get("prefecture") or conditions.get("region") or "",
        "municipality": location.get("municipality") or "",
        "planning_start_date": planning.get("start_date") or "",
    }
    return (
        "次の栽培条件に適用できる日本の公的な栽培根拠をWeb検索してください。"
        "農林水産省、農研機構、都道府県・市町村の農業試験場または普及機関の資料だけを使用してください。"
        "通販、個人ブログ、まとめ記事、掲示板は使用しないでください。対象地域・作型が異なる資料は、その相違を明記してください。"
        "薬剤の商品名、希釈倍率、使用回数は農薬登録候補として提案しないでください。"
        "定植済みの場合は定植直後の作業ではなく、計画開始日時点の管理、季節管理、潅水、施肥、剪定、病害虫の観察判断に関係する要点を優先してください。"
        "出力はMarkdownを使わず、次のJSONだけにしてください。"
        '{"summary":["条件に適用できる簡潔な要点"],"assumptions":["地域・作型の相違や未確認事項"],'
        '"sources":[{"title":"資料名","url":"https://...","publisher":"発行者",'
        '"applicable_region":"適用地域","published_at":"資料に明記された発行・改訂日。不明なら空文字"}]}\n'
        f"栽培条件:\n{json.dumps(facts, ensure_ascii=False, indent=2)}"
    )


def _parse_response(response: dict, *, context: dict, fetched_at: str):
    if not isinstance(response, dict):
        raise ValueError("crop knowledge response must be an object")
    output_texts = []
    api_sources = []
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "web_search_call":
            action = item.get("action") if isinstance(item.get("action"), dict) else {}
            api_sources.extend(action.get("sources") or [])
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if isinstance(content.get("text"), str):
                output_texts.append(content["text"])
            for annotation in content.get("annotations") or []:
                if isinstance(annotation, dict) and annotation.get("type") == "url_citation":
                    api_sources.append(annotation)
    if not output_texts and isinstance(response.get("output_text"), str):
        output_texts.append(response["output_text"])
    parsed = _parse_json_object("\n".join(output_texts))
    summary = _clean_text_list(parsed.get("summary"), MAX_SUMMARY_ITEMS, 600)
    assumptions = _clean_text_list(parsed.get("assumptions"), MAX_SUMMARY_ITEMS, 400)
    requested_region = _requested_region(context)
    candidates = list(parsed.get("sources") or []) + api_sources
    sources = []
    seen_urls = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        url = str(candidate.get("url") or "").strip()
        if not _is_trusted_source_url(url) or url in seen_urls:
            continue
        seen_urls.add(url)
        host = (urlparse(url).hostname or "").lower()
        sources.append(
            {
                "title": str(candidate.get("title") or host)[:300],
                "url": url[:1000],
                "publisher": str(candidate.get("publisher") or _publisher_for_host(host))[:180],
                "applicable_region": str(candidate.get("applicable_region") or requested_region)[:120],
                "published_at": str(candidate.get("published_at") or "")[:80],
                "fetched_at": fetched_at[:80],
            }
        )
        if len(sources) >= MAX_SOURCES:
            break
    if not sources:
        summary = []
        assumptions = []
    return {"summary": summary, "assumptions": assumptions, "sources": sources}


def _parse_json_object(text: str):
    text = str(text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("crop knowledge output must be a JSON object")
    return value


def _clean_text_list(value, limit: int, item_length: int):
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = str(item or "").strip()[:item_length]
        if text and text not in result:
            result.append(text)
    return result[:limit]


def _requested_region(context: dict):
    planting = context.get("planting") if isinstance(context.get("planting"), dict) else {}
    conditions = planting.get("conditions") if isinstance(planting.get("conditions"), dict) else {}
    field = context.get("field") if isinstance(context.get("field"), dict) else {}
    location = field.get("location") if isinstance(field.get("location"), dict) else {}
    return str(location.get("prefecture") or conditions.get("region") or "日本")


def _is_official_openai_base_url(base_url: str):
    host = (urlparse(base_url).hostname or "").lower()
    return host == "api.openai.com"


def _is_trusted_source_url(url: str):
    parsed = urlparse(str(url or ""))
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in TRUSTED_CROP_KNOWLEDGE_DOMAINS)


def _publisher_for_host(host: str):
    if host.endswith("naro.go.jp"):
        return "農研機構"
    if host.endswith("maff.go.jp"):
        return "農林水産省"
    return host


def _bounded_cache_days(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 30
    return min(max(number, 1), 365)


__instance = None


def crop_knowledge_provider():
    global __instance
    if __instance is None:
        __instance = CropKnowledgeProvider()
    return __instance
