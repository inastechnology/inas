import io
import math
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from PIL import Image, ImageDraw, ImageFont


class SensorTrendCardService:
    WIDTH = 1080
    HEIGHT = 1350
    MAX_IMPRESSION_CHARACTERS = 10
    METRIC_GROUPS = (
        ("soil_moisture_percent",),
        ("solar_radiation_w_m2", "par_umol_m2_s"),
        ("air_temperature_c", "soil_temperature_c"),
    )
    METRIC_STYLES = {
        "soil_moisture_percent": {"label": "土壌水分", "unit": "%", "color": "#39745B"},
        "solar_radiation_w_m2": {"label": "日射量", "unit": "W/m²", "color": "#D59A2E"},
        "par_umol_m2_s": {"label": "光量（PAR）", "unit": "µmol/m²/s", "color": "#D59A2E"},
        "air_temperature_c": {"label": "気温", "unit": "℃", "color": "#C96E4B"},
        "soil_temperature_c": {"label": "地温", "unit": "℃", "color": "#C96E4B"},
    }
    METRIC_SHORT_LABELS = {
        "soil_moisture_percent": "水分",
        "solar_radiation_w_m2": "日射",
        "par_umol_m2_s": "光量",
        "air_temperature_c": "気温",
        "soil_temperature_c": "地温",
    }
    EDITORIAL_ANGLES = {
        "change": {"label": "最初と最新を比較", "instruction": "期間の最初と最新の値の差に注目する"},
        "range": {"label": "3日間の振れ幅", "instruction": "3日間の最小値と最大値の幅に注目する"},
        "latest": {"label": "最新値と平均", "instruction": "最新値と3日平均を並べて見る"},
    }
    FONT_CANDIDATES = (
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    LATIN_FONT_CANDIDATES = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    )

    def __init__(self, font_path: str | None = None):
        self.font_path = font_path or self._find_font_path()
        self.latin_font_path = self._find_latin_font_path()

    def build_series(
        self,
        measurements: list[dict],
        *,
        start_at: datetime,
        end_at: datetime,
        device_names: dict[str, str] | None = None,
    ):
        device_names = device_names or {}
        normalized = []
        for measurement in measurements:
            metric = str(measurement.get("metric") or "")
            if metric not in self.METRIC_STYLES or measurement.get("quality", "ok") != "ok":
                continue
            measured_at = self._parse_datetime(measurement.get("measured_at"), start_at.tzinfo)
            value = self._safe_number(measurement.get("value"))
            if measured_at is None or value is None or measured_at < start_at or measured_at > end_at:
                continue
            normalized.append(
                {
                    "metric": metric,
                    "device_id": str(measurement.get("device_id") or ""),
                    "measured_at": measured_at,
                    "value": value,
                }
            )

        result = []
        for metric_group in self.METRIC_GROUPS:
            selected = self._select_metric_source(normalized, metric_group)
            if selected is None:
                continue
            metric, device_id, source_rows = selected
            points = self._hourly_points(source_rows)
            if not points:
                continue
            style = self.METRIC_STYLES[metric]
            values = [point["value"] for point in points]
            result.append(
                {
                    "metric": metric,
                    "label": style["label"],
                    "unit": style["unit"],
                    "color": style["color"],
                    "device_id": device_id,
                    "device_name": device_names.get(device_id) or device_id,
                    "points": points,
                    "minimum": min(values),
                    "maximum": max(values),
                    "average": sum(values) / len(values),
                    "first": values[0],
                    "last": values[-1],
                }
            )
        return result

    def summarize_for_ai(self, series: list[dict]):
        return [
            {
                "metric": item["metric"],
                "label": item["label"],
                "unit": item["unit"],
                "point_count": len(item["points"]),
                "minimum": round(item["minimum"], 2),
                "maximum": round(item["maximum"], 2),
                "average": round(item["average"], 2),
                "first": round(item["first"], 2),
                "last": round(item["last"], 2),
                "change": round(item["last"] - item["first"], 2),
            }
            for item in series
        ]

    def build_editorial_context(
        self,
        series: list[dict],
        *,
        end_at: datetime,
        previous_focus_metric: str | None = None,
    ):
        if not series:
            return {}
        metric_order = [item["metric"] for item in series]
        if previous_focus_metric in metric_order and len(metric_order) > 1:
            focus_index = (metric_order.index(previous_focus_metric) + 1) % len(metric_order)
        else:
            focus_index = end_at.date().toordinal() % len(metric_order)
        focus = series[focus_index]
        angle_names = tuple(self.EDITORIAL_ANGLES)
        angle = angle_names[(end_at.date().toordinal() // len(metric_order)) % len(angle_names)]
        delta = focus["last"] - focus["first"]
        tolerance = max(abs(focus["maximum"] - focus["minimum"]) * 0.05, 0.1)
        direction = "ほぼ横ばい" if abs(delta) <= tolerance else ("上向き" if delta > 0 else "下向き")
        return {
            "focus_metric": focus["metric"],
            "focus_label": focus["label"],
            "focus_short_label": self.METRIC_SHORT_LABELS.get(focus["metric"], focus["label"]),
            "angle": angle,
            "angle_label": self.EDITORIAL_ANGLES[angle]["label"],
            "instruction": self.EDITORIAL_ANGLES[angle]["instruction"],
            "direction": direction,
            "first": round(focus["first"], 2),
            "last": round(focus["last"], 2),
            "minimum": round(focus["minimum"], 2),
            "maximum": round(focus["maximum"], 2),
            "average": round(focus["average"], 2),
            "change": round(delta, 2),
            "unit": focus["unit"],
        }

    @staticmethod
    def prioritize_series(series: list[dict], editorial_context: dict):
        focus_metric = editorial_context.get("focus_metric")
        return sorted(series, key=lambda item: item.get("metric") != focus_metric)

    def choose_impression(
        self,
        value: str | None,
        series: list[dict],
        *,
        editorial_context: dict | None = None,
        recent_impressions: list[str] | None = None,
    ):
        recent = [cleaned for item in (recent_impressions or []) if (cleaned := self.clean_impression(item))]
        cleaned = self.clean_impression(value)
        if cleaned and not self._is_similar_to_recent(cleaned, recent):
            return cleaned
        for candidate in self._fallback_impression_candidates(series, editorial_context or {}):
            if not self._is_similar_to_recent(candidate, recent):
                return candidate
        return self._fallback_impression_candidates(series, editorial_context or {})[0]

    def render_jpeg(
        self,
        series: list[dict],
        impression: str,
        *,
        start_at: datetime,
        end_at: datetime,
        editorial_context: dict | None = None,
    ):
        if not series:
            raise ValueError("at least one sensor series is required")
        impression = self.clean_impression(impression) or self.fallback_impression(series)
        image = Image.new("RGB", (self.WIDTH, self.HEIGHT), "#F4EFE5")
        draw = ImageDraw.Draw(image)
        title_font = self._font(34)
        impression_font = self._font(78)
        subtitle_font = self._font(26)
        metric_font = self._font(31)
        value_font = self._font(27)
        small_font = self._font(20)

        self._draw_text(draw, (64, 50), "INAS FIELD NOTE", title_font, "#7B856D")
        self._draw_centered_text(draw, impression, 145, impression_font, "#294B3D")
        editorial_context = editorial_context or {}
        focus_label = editorial_context.get("focus_label")
        angle_label = editorial_context.get("angle_label")
        subtitle = f"今日の注目：{focus_label}｜{angle_label}" if focus_label and angle_label else "直近3日のセンサー記録"
        self._draw_centered_text(draw, subtitle, 236, subtitle_font, "#526257")
        date_range = f"{start_at:%m/%d %H:%M}  —  {end_at:%m/%d %H:%M}"
        self._draw_centered_text(draw, date_range, 276, small_font, "#788078")

        cards_top = 320
        cards_bottom = 1248
        gap = 22
        card_height = (cards_bottom - cards_top - gap * (len(series) - 1)) // len(series)
        for index, item in enumerate(series):
            top = cards_top + index * (card_height + gap)
            self._draw_series_card(
                draw,
                item,
                left=58,
                top=top,
                width=964,
                height=card_height,
                start_at=start_at,
                end_at=end_at,
                metric_font=metric_font,
                value_font=value_font,
                small_font=small_font,
            )

        self._draw_centered_text(draw, "取得できたセンサー値を1時間ごとに平均", 1302, small_font, "#788078")
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=92, optimize=True, progressive=True)
        return output.getvalue()

    def build_caption(
        self,
        series: list[dict],
        impression: str,
        *,
        start_at: datetime,
        end_at: datetime,
        editorial_context: dict | None = None,
    ):
        labels = "・".join(item["label"] for item in series)
        impression = self.clean_impression(impression) or self.fallback_impression(series)
        editorial_context = editorial_context or self.build_editorial_context(series, end_at=end_at)
        focus_text = self._editorial_fact(editorial_context)
        focus_hashtag = self._metric_hashtag(editorial_context.get("focus_metric"))
        return (
            f"{start_at.month}月{start_at.day}日〜{end_at.month}月{end_at.day}日の記録から、今日は{focus_text}。"
            f"{labels}を1時間平均でまとめています。\n"
            f"「{impression}」\n"
            f"#スマート農業 #センサー記録 #{focus_hashtag} #栽培記録"
        )

    @classmethod
    def clean_impression(cls, value: str | None):
        cleaned = re.sub(r"\s+", "", str(value or "")).strip("「」『』\"'`。.!！")
        if not cleaned or len(cleaned) > cls.MAX_IMPRESSION_CHARACTERS:
            return ""
        return cleaned

    @staticmethod
    def fallback_impression(series: list[dict]):
        if not series:
            return "今日も見守り中"
        changes = []
        for item in series:
            span = max(abs(item["maximum"] - item["minimum"]), abs(item["average"]), 1.0)
            changes.append(abs(item["last"] - item["first"]) / span)
        return "変化を見守ろう" if max(changes, default=0.0) >= 0.2 else "今日も穏やか"

    def _fallback_impression_candidates(self, series: list[dict], editorial_context: dict):
        short_label = str(editorial_context.get("focus_short_label") or "変化")
        direction = editorial_context.get("direction")
        angle = editorial_context.get("angle")
        candidates = {
            "change": [f"{short_label}は{direction}", f"{short_label}の差を追う", f"{short_label}の動きを記録"],
            "range": [f"{short_label}の幅に注目", f"{short_label}の波を追う", f"{short_label}の揺れを記録"],
            "latest": [f"{short_label}の今を記録", f"今の{short_label}を見る", f"{short_label}を今日も確認"],
        }.get(angle, [])
        candidates.extend([self.fallback_impression(series), "小さな変化を記録", "今日の動きを確認"])
        cleaned = [self.clean_impression(candidate) for candidate in candidates]
        return [candidate for candidate in cleaned if candidate]

    @staticmethod
    def _is_similar_to_recent(candidate: str, recent: list[str]):
        return any(candidate == previous or SequenceMatcher(None, candidate, previous).ratio() >= 0.72 for previous in recent)

    @staticmethod
    def _editorial_fact(editorial_context: dict):
        label = editorial_context.get("focus_label") or "センサー値"
        unit = editorial_context.get("unit") or ""
        angle = editorial_context.get("angle")
        if angle == "change":
            return f"{label}の最初の値{editorial_context.get('first'):g}{unit}と最新値{editorial_context.get('last'):g}{unit}を比べました"
        if angle == "range":
            return f"{label}の振れ幅（{editorial_context.get('minimum'):g}〜{editorial_context.get('maximum'):g}{unit}）に注目しました"
        if angle == "latest":
            return f"{label}の最新値{editorial_context.get('last'):g}{unit}と3日平均{editorial_context.get('average'):g}{unit}を見ました"
        return f"{label}に注目しました"

    @staticmethod
    def _metric_hashtag(metric: str | None):
        return {
            "soil_moisture_percent": "土壌水分",
            "solar_radiation_w_m2": "日射量",
            "par_umol_m2_s": "PAR",
            "air_temperature_c": "気温",
            "soil_temperature_c": "地温",
        }.get(metric, "植物観察")

    def _draw_series_card(
        self,
        draw,
        item,
        *,
        left,
        top,
        width,
        height,
        start_at,
        end_at,
        metric_font,
        value_font,
        small_font,
    ):
        right = left + width
        bottom = top + height
        draw.rounded_rectangle((left, top, right, bottom), radius=30, fill="#FFFCF6", outline="#E4DDD0", width=2)
        self._draw_text(draw, (left + 38, top + 25), item["label"], metric_font, "#263C33")
        latest = f"{item['last']:.1f} {item['unit']}"
        latest_box = self._textbbox(draw, latest, value_font)
        self._draw_text(draw, (right - 38 - (latest_box[2] - latest_box[0]), top + 29), latest, value_font, item["color"])
        device_name = str(item["device_name"])
        if len(device_name) > 24:
            device_name = f"{device_name[:23]}…"
        source = f"{device_name}  •  平均 {item['average']:.1f} {item['unit']}"
        self._draw_text(draw, (left + 38, top + 68), source, small_font, "#7C827D")

        plot_left = left + 62
        plot_right = right - 38
        plot_top = top + 112
        plot_bottom = bottom - 48
        values = [point["value"] for point in item["points"]]
        nonnegative_metric = item["metric"] in {"soil_moisture_percent", "solar_radiation_w_m2", "par_umol_m2_s"}
        value_min, value_max = self._value_range(values, floor=0.0 if nonnegative_metric else None)

        for tick in range(4):
            ratio = tick / 3
            x = plot_left + (plot_right - plot_left) * ratio
            draw.line((x, plot_top, x, plot_bottom), fill="#ECE6DC", width=2)
            tick_at = start_at + (end_at - start_at) * ratio
            label = f"{tick_at.month}/{tick_at.day}"
            box = self._textbbox(draw, label, small_font)
            self._draw_text(draw, (x - (box[2] - box[0]) / 2, plot_bottom + 10), label, small_font, "#8A8C87")
        for ratio in (0.0, 0.5, 1.0):
            y = plot_bottom - (plot_bottom - plot_top) * ratio
            draw.line((plot_left, y, plot_right, y), fill="#ECE6DC", width=2)

        total_seconds = max((end_at - start_at).total_seconds(), 1.0)
        points = []
        for point in item["points"]:
            x_ratio = max(0.0, min(1.0, (point["at"] - start_at).total_seconds() / total_seconds))
            y_ratio = (point["value"] - value_min) / (value_max - value_min)
            points.append((plot_left + (plot_right - plot_left) * x_ratio, plot_bottom - (plot_bottom - plot_top) * y_ratio))
        if len(points) > 1:
            draw.line(points, fill=item["color"], width=6, joint="curve")
        for x, y in (points[0], points[-1]):
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=item["color"], outline="#FFFCF6", width=3)

        high_label = f"{value_max:.1f}"
        low_label = f"{value_min:.1f}"
        self._draw_text(draw, (plot_left + 7, plot_top + 4), high_label, small_font, "#8A8C87")
        self._draw_text(draw, (plot_left + 7, plot_bottom - 27), low_label, small_font, "#8A8C87")

    def _font(self, size: int):
        if self.font_path:
            return ImageFont.truetype(self.font_path, size=size)
        return ImageFont.load_default(size=size)

    def _latin_font(self, size: int):
        if self.latin_font_path:
            return ImageFont.truetype(self.latin_font_path, size=size)
        return self._font(size)

    @classmethod
    def _find_font_path(cls):
        configured = os.environ.get("INSTAGRAM_SENSOR_GRAPH_FONT_PATH", "").strip()
        for path in (configured, *cls.FONT_CANDIDATES):
            if path and os.path.isfile(path):
                return path
        return None

    @classmethod
    def _find_latin_font_path(cls):
        for path in cls.LATIN_FONT_CANDIDATES:
            if os.path.isfile(path):
                return path
        return None

    def _draw_centered_text(self, draw, text, center_y, font, fill):
        box = self._textbbox(draw, text, font)
        width = box[2] - box[0]
        height = box[3] - box[1]
        self._draw_text(draw, ((self.WIDTH - width) / 2, center_y - height / 2 - box[1]), text, font, fill)

    def _draw_text(self, draw, position, text, font, fill):
        x, y = position
        for latin, run in self._font_runs(str(text)):
            run_font = self._latin_font(font.size) if latin else font
            draw.text((x, y), run, fill=fill, font=run_font)
            x += draw.textlength(run, font=run_font)

    def _textbbox(self, draw, text, font):
        width = 0.0
        top = 0
        bottom = 0
        for latin, run in self._font_runs(str(text)):
            run_font = self._latin_font(font.size) if latin else font
            box = draw.textbbox((0, 0), run, font=run_font)
            width += draw.textlength(run, font=run_font)
            top = min(top, box[1])
            bottom = max(bottom, box[3])
        return 0, top, width, bottom

    @classmethod
    def _font_runs(cls, text):
        runs = []
        for character in text:
            latin = not cls._is_japanese_character(character)
            if runs and runs[-1][0] == latin:
                runs[-1] = (latin, runs[-1][1] + character)
            else:
                runs.append((latin, character))
        return runs

    @staticmethod
    def _is_japanese_character(character):
        codepoint = ord(character)
        return 0x3000 <= codepoint <= 0x30FF or 0x3400 <= codepoint <= 0x9FFF or 0xF900 <= codepoint <= 0xFAFF or 0xFF00 <= codepoint <= 0xFFEF

    @staticmethod
    def _value_range(values, floor=None):
        minimum = min(values)
        maximum = max(values)
        span = maximum - minimum
        padding = max(span * 0.12, abs(maximum) * 0.03, 1.0)
        lower = minimum - padding
        if floor is not None:
            lower = max(floor, lower)
        return lower, maximum + padding

    @classmethod
    def _select_metric_source(cls, measurements, metric_group):
        fallback = None
        for metric in metric_group:
            by_device = defaultdict(list)
            for measurement in measurements:
                if measurement["metric"] == metric:
                    by_device[measurement["device_id"]].append(measurement)
            if not by_device:
                continue
            device_id, rows = max(
                by_device.items(),
                key=lambda item: (len(item[1]), max(row["measured_at"] for row in item[1]), item[0]),
            )
            rows.sort(key=lambda row: row["measured_at"])
            fallback = fallback or (metric, device_id, rows)
            if len(rows) >= 2:
                return metric, device_id, rows
        return fallback

    @staticmethod
    def _hourly_points(rows):
        buckets = defaultdict(list)
        for row in rows:
            bucket = row["measured_at"].replace(minute=0, second=0, microsecond=0)
            buckets[bucket].append(row["value"])
        return [{"at": at, "value": sum(values) / len(values)} for at, values in sorted(buckets.items())]

    @staticmethod
    def _parse_datetime(value, fallback_timezone):
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=fallback_timezone)
        elif fallback_timezone is not None:
            parsed = parsed.astimezone(fallback_timezone)
        return parsed

    @staticmethod
    def _safe_number(value):
        if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
            return None
        return float(value)


def default_sensor_trend_window(end_at: datetime):
    return end_at - timedelta(days=3), end_at
