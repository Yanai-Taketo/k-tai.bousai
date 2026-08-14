"""実電文フィクスチャによるゴールデンテスト。

フィクスチャはすべて気象庁防災情報XMLの実電文(2026-08採取)または公式サンプル電文。
新体系(2026-05-29運用開始)の警報コード・名称が正しく解析されることを担保する。
"""

import datetime
import os
import unittest

from generator import freshness
from generator.jmautil import JST
from generator.offices import OFFICES
from generator.parse_eqtsunami import parse_vtse41, parse_vxse51, parse_vxse53
from generator.parse_forecast import parse_vpfd51, parse_vpfw50
from generator.parse_sokuho import parse_sokuho
from generator.parse_warnings import merge_office, parse_vpwwxx, severity_of

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(FIX, name), "rb") as f:
        return f.read()


class TestWarnings(unittest.TestCase):
    def test_vpww55_tokubetsu_keiho(self):
        """千葉県大雨(2026-08-13実電文): レベル5特別警報・レベル4危険警報を含む。"""
        p = parse_vpwwxx(fixture("VPWW55_chiba.xml"))
        self.assertEqual(p["version"], "1.5_0")
        self.assertEqual(p["anomalies"], [])
        names = {k["name"] for _a, ks in p["areas"] for k in ks}
        codes = {k["code"] for _a, ks in p["areas"] for k in ks}
        self.assertIn("レベル５大雨特別警報", names)
        self.assertIn("33", codes)
        self.assertIn("43", codes)  # レベル４大雨危険警報
        self.assertTrue(p["headline"].startswith("【特別警報(大雨)】") or "特別警報" in p["headline"])

    def test_vpww56_dosha(self):
        p = parse_vpwwxx(fixture("VPWW56_chiba.xml"))
        codes = {k["code"] for _a, ks in p["areas"] for k in ks}
        self.assertIn("49", codes)  # レベル４土砂災害危険警報
        names = {k["name"] for _a, ks in p["areas"] for k in ks}
        self.assertIn("レベル４土砂災害危険警報", names)

    def test_vpww57_takashio(self):
        p = parse_vpwwxx(fixture("VPWW57_kagawa.xml"))
        self.assertTrue(p["areas"])

    def test_vpww61_sonota(self):
        p = parse_vpwwxx(fixture("VPWW61_niigata.xml"))
        names = [k["name"] for _a, ks in p["areas"] for k in ks]
        self.assertTrue(all("注意報" in n for n in names), names)

    def test_severity(self):
        self.assertEqual(severity_of("レベル５大雨特別警報"), 5)
        self.assertEqual(severity_of("レベル４土砂災害危険警報"), 4)
        self.assertEqual(severity_of("レベル３大雨警報"), 3)
        self.assertEqual(severity_of("暴風警報"), 3)
        self.assertEqual(severity_of("レベル２大雨注意報"), 2)
        self.assertEqual(severity_of("濃霧注意報"), 2)

    def test_legacy_flood_code_detected(self):
        """新電文に洪水コード04/18が現れたら異常として報告する(§8.2)。"""
        xml = (
            '<Report xmlns="http://xml.kishou.go.jp/jmaxml1/">'
            "<Head><Title>t</Title><ReportDateTime>2026-08-14T00:00:00+09:00</ReportDateTime>"
            "<InfoKindVersion>1.5_0</InfoKindVersion></Head>"
            '<Body><Warning type="気象警報・注意報(市町村等をまとめた地域等)">'
            "<Item><Kind><Name>洪水警報</Name><Code>04</Code><Status>発表</Status></Kind>"
            "<Area><Name>テスト</Name></Area></Item></Warning></Body></Report>"
        ).encode()
        p = parse_vpwwxx(xml)
        self.assertTrue(any("04" in a for a in p["anomalies"]))

    def test_unexpected_version_detected(self):
        xml = (
            '<Report xmlns="http://xml.kishou.go.jp/jmaxml1/">'
            "<Head><Title>t</Title><ReportDateTime>2026-08-14T00:00:00+09:00</ReportDateTime>"
            "<InfoKindVersion>9.9_9</InfoKindVersion></Head><Body/></Report>"
        ).encode()
        p = parse_vpwwxx(xml)
        self.assertTrue(any("InfoKindVersion" in a for a in p["anomalies"]))

    def test_merge_office(self):
        parses = [
            parse_vpwwxx(fixture("VPWW55_chiba.xml")),
            parse_vpwwxx(fixture("VPWW56_chiba.xml")),
        ]
        m = merge_office(parses)
        self.assertEqual(m["max_severity"], 5)
        self.assertTrue(m["report_dt"])
        area_names = [a for a, _k in m["areas"]]
        self.assertEqual(len(area_names), len(set(area_names)), "区域の重複なし")


class TestEqTsunami(unittest.TestCase):
    def test_vxse53(self):
        q = parse_vxse53(fixture("VXSE53_sample.xml"))
        self.assertTrue(q["origin"])
        self.assertTrue(q["hypo"])
        self.assertTrue(q["maxint"])
        self.assertTrue(q["event_id"])

    def test_vxse51(self):
        q = parse_vxse51(fixture("VXSE51_sample.xml"))
        self.assertTrue(q["maxint"])
        self.assertEqual(q["kind"], "震度速報")

    def test_vtse41_warning(self):
        """公式サンプル(大津波警報)は active=True でなければならない。"""
        t = parse_vtse41(fixture("VTSE41_sample_warning.xml"))
        self.assertTrue(t["active"])
        kinds = {i["kind"] for i in t["items"]}
        self.assertIn("大津波警報", kinds)
        self.assertTrue(any(i["areas"] for i in t["items"]))

    def test_vtse41_cancel(self):
        """取消電文は active=False。"""
        t = parse_vtse41(fixture("VTSE41_sample_cancel.xml"))
        self.assertFalse(t["active"])


class TestForecast(unittest.TestCase):
    def test_vpfd51(self):
        f = parse_vpfd51(fixture("VPFD51_tokyo.xml"))
        self.assertTrue(f["report_dt"])
        names = [a["name"] for a in f["areas"]]
        self.assertIn("東京地方", names)
        tokyo = f["areas"][names.index("東京地方")]
        self.assertGreaterEqual(len(tokyo["weathers"]), 2)
        self.assertTrue(all(t and w for t, w in tokyo["weathers"]))
        self.assertTrue(tokyo["pops"])
        self.assertTrue(f["stations"])
        self.assertTrue(any(s["name"] == "東京" for s in f["stations"]))

    def test_vpfw50(self):
        f = parse_vpfw50(fixture("VPFW50_tokyo.xml"))
        self.assertTrue(f["areas"])
        a = f["areas"][0]
        self.assertGreaterEqual(len(a["days"]), 5)
        self.assertTrue(any(wx for _d, wx, _p in a["days"]))


class TestSokuho(unittest.TestCase):
    def test_vpbs50(self):
        s = parse_sokuho(fixture("VPBS50_chiba.xml"))
        self.assertIn("線状降水帯", s["title"])
        self.assertTrue(s["text"])
        self.assertTrue(s["report_dt"])

    def test_vphw50(self):
        s = parse_sokuho(fixture("VPHW50_sample.xml"))
        self.assertIn("竜巻", s["title"])
        self.assertTrue(s["text"])


class TestFreshness(unittest.TestCase):
    def test_fresh_and_stale(self):
        now = datetime.datetime(2026, 8, 14, 12, 0, tzinfo=JST)
        stale, age = freshness.check("2026-08-14T11:30:00+09:00", now)
        self.assertFalse(stale)
        self.assertEqual(age, 30)
        stale, age = freshness.check("2026-08-14T09:00:00+09:00", now)
        self.assertTrue(stale)
        stale, _age = freshness.check("", now)
        self.assertTrue(stale)


class TestOffices(unittest.TestCase):
    def test_58_offices(self):
        self.assertEqual(len(OFFICES), 58)
        # 分割官署の対応(警報と天気予報で区分が異なる)
        self.assertEqual(OFFICES["014030"], ("十勝地方", "014100"))
        self.assertEqual(OFFICES["460040"], ("奄美地方", "460100"))
        # 全予報官署コードがOFFICESのキーに存在する(自己参照整合)
        for _code, (_name, fc) in OFFICES.items():
            self.assertIn(fc, OFFICES)


if __name__ == "__main__":
    unittest.main()
