from datetime import datetime
from urllib import error, request
from xml.etree import ElementTree

from ina_device_hub.general_log import logger


class WeatherForecastService:
    DEFAULT_FORECAST_URL = "https://www.data.jma.go.jp/developer/xml/feed/regular.xml"
    DEFAULT_AREA_NAME = "東予"
    DEFAULT_OFFICE_NAME = "松山地方気象台"
    DEFAULT_FORECAST_TITLE = "府県天気予報"
    NS = {
        "jmx": "http://xml.kishou.go.jp/jmaxml1/",
        "ib": "http://xml.kishou.go.jp/jmaxml1/informationBasis1/",
        "body": "http://xml.kishou.go.jp/jmaxml1/body/meteorology1/",
        "eb": "http://xml.kishou.go.jp/jmaxml1/elementBasis1/",
    }
    ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

    def __init__(
        self,
        forecast_url: str | None = None,
        area_name: str | None = None,
        office_name: str | None = None,
        forecast_title: str | None = None,
    ):
        self.forecast_url = (forecast_url or self.DEFAULT_FORECAST_URL).strip()
        self.area_name = (area_name or self.DEFAULT_AREA_NAME).strip()
        self.office_name = (office_name or self.DEFAULT_OFFICE_NAME).strip()
        self.forecast_title = (forecast_title or self.DEFAULT_FORECAST_TITLE).strip()

    def fetch_forecast(self):
        xml_text, selected_forecast_url = self._fetch_xml()
        forecast = self.parse_forecast(xml_text)
        forecast["feed_url"] = self.forecast_url if selected_forecast_url != self.forecast_url else None
        forecast["forecast_url"] = selected_forecast_url
        forecast["office"] = self.office_name
        return forecast

    def parse_forecast(self, xml_text: str):
        root = ElementTree.fromstring(xml_text)
        forecast = {
            "source": "jma_xml",
            "area": self.area_name,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "report_datetime": self._find_text(root, ".//ib:ReportDateTime"),
            "target_datetime": self._find_text(root, ".//ib:TargetDateTime"),
            "daily_weather": [],
            "precipitation_probabilities": [],
            "privacy_note": "Area-level forecast only. Station names, station codes, addresses, and point temperature data are omitted.",
        }

        for time_series in root.findall(".//body:TimeSeriesInfo", self.NS):
            time_defines = self._build_time_defines(time_series)
            for item in time_series.findall("body:Item", self.NS):
                if self._item_area_name(item) != self.area_name:
                    continue
                property_type = self._find_text(item, "body:Kind/body:Property/body:Type")
                if property_type == "天気":
                    forecast["daily_weather"] = self._parse_daily_weather(item, time_defines)
                elif property_type == "降水確率":
                    forecast["precipitation_probabilities"] = self._parse_precipitation(item, time_defines)

        return forecast

    def _fetch_xml(self):
        xml_text = self._fetch_url(self.forecast_url)
        if not self._is_atom_feed(xml_text):
            return xml_text, self.forecast_url

        forecast_url = self._select_forecast_url_from_feed(xml_text)
        return self._fetch_url(forecast_url), forecast_url

    def _fetch_url(self, url: str):
        req = request.Request(url, headers={"User-Agent": "ina-device-hub/1.0"})
        try:
            with request.urlopen(req, timeout=20) as response:
                return response.read().decode("utf-8")
        except error.URLError as exc:
            raise RuntimeError(f"Failed to fetch weather forecast from {url}: {exc}") from exc

    def _is_atom_feed(self, xml_text: str):
        root = ElementTree.fromstring(xml_text)
        return root.tag == "{http://www.w3.org/2005/Atom}feed"

    def _select_forecast_url_from_feed(self, feed_xml_text: str):
        root = ElementTree.fromstring(feed_xml_text)
        for entry in root.findall("atom:entry", self.ATOM_NS):
            title = self._find_atom_text(entry, "atom:title")
            author_name = self._find_atom_text(entry, "atom:author/atom:name")
            if author_name != self.office_name or self.forecast_title not in title:
                continue

            link = entry.find("atom:link[@type='application/xml']", self.ATOM_NS)
            if link is not None and link.get("href"):
                return link.get("href")
            entry_id = self._find_atom_text(entry, "atom:id")
            if entry_id:
                return entry_id

        raise RuntimeError(f"Failed to find JMA forecast feed entry: office={self.office_name}, title={self.forecast_title}")

    def _parse_daily_weather(self, item, time_defines: dict):
        weather_by_ref = {
            weather.get("refID"): (weather.text or "").strip() for weather in item.findall(".//body:WeatherPart/eb:Weather", self.NS) if weather.get("refID")
        }
        sentence_by_ref = {
            part.get("refID"): self._find_text(part, "body:Sentence") for part in item.findall(".//body:WeatherForecastPart", self.NS) if part.get("refID")
        }
        return [
            {
                "name": time_define.get("name"),
                "date_time": time_define.get("date_time"),
                "weather": weather,
                "sentence": sentence_by_ref.get(ref_id) or weather,
            }
            for ref_id, weather in weather_by_ref.items()
            for time_define in [time_defines.get(ref_id, {})]
        ]

    def _parse_precipitation(self, item, time_defines: dict):
        probabilities = []
        for probability in item.findall(".//body:ProbabilityOfPrecipitationPart/eb:ProbabilityOfPrecipitation", self.NS):
            ref_id = probability.get("refID")
            time_define = time_defines.get(ref_id, {})
            probabilities.append(
                {
                    "name": time_define.get("name"),
                    "date_time": time_define.get("date_time"),
                    "duration": time_define.get("duration"),
                    "probability_percent": self._parse_int(probability.text),
                }
            )
        return probabilities

    def _build_time_defines(self, time_series):
        defines = {}
        for time_define in time_series.findall("body:TimeDefines/body:TimeDefine", self.NS):
            time_id = time_define.get("timeId")
            if not time_id:
                continue
            defines[time_id] = {
                "date_time": self._find_text(time_define, "body:DateTime"),
                "duration": self._find_text(time_define, "body:Duration"),
                "name": self._find_text(time_define, "body:Name"),
            }
        return defines

    def _item_area_name(self, item):
        return self._find_text(item, "body:Area/body:Name")

    def _find_text(self, element, path):
        found = element.find(path, self.NS)
        if found is None or found.text is None:
            return None
        return found.text.strip()

    def _find_atom_text(self, element, path):
        found = element.find(path, self.ATOM_NS)
        if found is None or found.text is None:
            return ""
        return found.text.strip()

    def _parse_int(self, value):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except ValueError:
            logger.warning(f"Invalid weather probability value: {value}")
            return None


def weather_forecast_service(
    forecast_url: str | None = None,
    area_name: str | None = None,
    office_name: str | None = None,
    forecast_title: str | None = None,
):
    return WeatherForecastService(
        forecast_url=forecast_url,
        area_name=area_name,
        office_name=office_name,
        forecast_title=forecast_title,
    )
