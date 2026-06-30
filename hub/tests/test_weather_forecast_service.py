import os
import tempfile
import unittest

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "x")
os.environ.setdefault("TURSO_AUTH_TOKEN", "x")
os.environ.setdefault("S3_ENDPOINT_URL", "x")
os.environ.setdefault("S3_BUCKET_NAME", "x")
os.environ.setdefault("S3_BUCKET_REGION", "auto")
os.environ.setdefault("S3_ACCESS_KEY", "x")
os.environ.setdefault("S3_SECRET_KEY", "x")
os.environ.setdefault("MQTT_BROKER_URL", "localhost")
os.environ.setdefault("MQTT_BROKER_PORT", "1883")
os.environ.setdefault("MQTT_BROKER_USERNAME", "x")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "x")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")

from ina_device_hub.weather_forecast_service import WeatherForecastService  # noqa: E402


class WeatherForecastServiceTest(unittest.TestCase):
    def test_fetch_forecast_selects_matching_jma_feed_entry(self):
        feed_xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" lang="ja">
  <entry>
    <title>府県天気予報（Ｒ１）</title>
    <author><name>高松地方気象台</name></author>
    <link type="application/xml" href="https://example.test/kagawa.xml"/>
  </entry>
  <entry>
    <title>府県天気予報（Ｒ１）</title>
    <author><name>松山地方気象台</name></author>
    <link type="application/xml" href="https://example.test/ehime.xml"/>
  </entry>
</feed>
"""
        forecast_xml = self._forecast_xml()
        requested_urls = []

        class StubWeatherForecastService(WeatherForecastService):
            def _fetch_url(self, url: str):
                requested_urls.append(url)
                return {
                    "https://example.test/feed.xml": feed_xml,
                    "https://example.test/ehime.xml": forecast_xml,
                }[url]

        forecast = StubWeatherForecastService(
            forecast_url="https://example.test/feed.xml",
            area_name="東予",
            office_name="松山地方気象台",
            forecast_title="府県天気予報",
        ).fetch_forecast()

        self.assertEqual(
            requested_urls,
            ["https://example.test/feed.xml", "https://example.test/ehime.xml"],
        )
        self.assertEqual(forecast["forecast_url"], "https://example.test/ehime.xml")
        self.assertEqual(forecast["feed_url"], "https://example.test/feed.xml")
        self.assertEqual(forecast["office"], "松山地方気象台")
        self.assertEqual(forecast["daily_weather"][0]["weather"], "くもり後晴れ")

    def test_parse_forecast_extracts_area_level_weather_only(self):
        forecast = WeatherForecastService(area_name="東予").parse_forecast(self._forecast_xml())

        self.assertEqual(forecast["area"], "東予")
        self.assertEqual(
            [item["weather"] for item in forecast["daily_weather"]],
            ["くもり後晴れ", "晴れ後くもり"],
        )
        self.assertEqual(
            forecast["precipitation_probabilities"][0]["probability_percent"],
            40,
        )
        self.assertNotIn("新居浜", str(forecast))

    def _forecast_xml(self):
        return """<?xml version="1.0" encoding="UTF-8"?>
<Report xmlns="http://xml.kishou.go.jp/jmaxml1/" xmlns:jmx_eb="http://xml.kishou.go.jp/jmaxml1/elementBasis1/">
  <Head xmlns="http://xml.kishou.go.jp/jmaxml1/informationBasis1/">
    <ReportDateTime>2026-05-01T11:00:00+09:00</ReportDateTime>
    <TargetDateTime>2026-05-01T11:00:00+09:00</TargetDateTime>
  </Head>
  <Body xmlns="http://xml.kishou.go.jp/jmaxml1/body/meteorology1/">
    <MeteorologicalInfos type="区域予報">
      <TimeSeriesInfo>
        <TimeDefines>
          <TimeDefine timeId="1"><DateTime>2026-05-01T11:00:00+09:00</DateTime><Name>今日</Name></TimeDefine>
          <TimeDefine timeId="2"><DateTime>2026-05-02T00:00:00+09:00</DateTime><Name>明日</Name></TimeDefine>
        </TimeDefines>
        <Item>
          <Kind><Property><Type>天気</Type><WeatherPart>
            <jmx_eb:Weather refID="1" type="天気">くもり後晴れ</jmx_eb:Weather>
            <jmx_eb:Weather refID="2" type="天気">晴れ後くもり</jmx_eb:Weather>
          </WeatherPart></Property></Kind>
          <Area><Name>東予</Name><Code>380020</Code></Area>
        </Item>
      </TimeSeriesInfo>
      <TimeSeriesInfo>
        <TimeDefines>
          <TimeDefine timeId="1"><DateTime>2026-05-01T12:00:00+09:00</DateTime><Duration>PT6H</Duration><Name>１２時から１８時まで</Name></TimeDefine>
        </TimeDefines>
        <Item>
          <Kind><Property><Type>降水確率</Type><ProbabilityOfPrecipitationPart>
            <jmx_eb:ProbabilityOfPrecipitation refID="1" type="６時間降水確率" unit="%">40</jmx_eb:ProbabilityOfPrecipitation>
          </ProbabilityOfPrecipitationPart></Property></Kind>
          <Area><Name>東予</Name><Code>380020</Code></Area>
        </Item>
      </TimeSeriesInfo>
    </MeteorologicalInfos>
    <MeteorologicalInfos type="地点予報">
      <TimeSeriesInfo>
        <Item><Kind><Property><Type>３時間毎気温</Type></Property></Kind><Station><Name>新居浜</Name><Code>73141</Code></Station></Item>
      </TimeSeriesInfo>
    </MeteorologicalInfos>
  </Body>
</Report>
"""


if __name__ == "__main__":
    unittest.main()
