"""台風解析・予報情報(VPTW60〜65)の解析と表示のテスト。

フィクスチャ:
  VPTW60_td.xml     … 実配信の実電文(熱帯低気圧化して消滅した台風)。
                       速度「ゆっくり」・半径「なし」など、数値でなく文字表現が
                       入る実際のケースを含む。
  VPTW60_active.xml … 公式解説資料の記載例に基づく合成電文(実況+予報)。
                       台風非発生期には実配信に完全な例が存在しないため。
"""

import datetime
import os
import unittest

from generator.jmautil import JST
from generator.main import within
from generator.parse_typhoon import display_name, parse_vptw
from generator.render import render_index, render_typhoon

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(FIX, name), "rb") as f:
        return f.read()


class TestParseTyphoon(unittest.TestCase):
    def test_active_typhoon(self):
        t = parse_vptw(fixture("VPTW60_active.xml"))
        self.assertEqual(t["event_id"], "TC2612")
        self.assertEqual(display_name(t), "台風第12号(ノグリー)")
        self.assertFalse(t["dissipated"])
        cur = t["infos"][0]
        self.assertEqual(cur["kind"], "実況")
        self.assertEqual(cur["location"], "南大東島の南南東約１６０ｋｍ")
        self.assertEqual(cur["intensity"], "強い")
        self.assertEqual(cur["coord"], "北緯２４．５度東経１３１．８度")
        self.assertEqual(cur["pressure"], "950")
        self.assertEqual(cur["wind_max"], "40")
        self.assertEqual(cur["wind_gust"], "60")
        self.assertEqual(cur["storm"], "全域110km")
        self.assertEqual(cur["gale"], "南東330km 北西220km")

    def test_forecast_rows(self):
        """予報では中心位置が予報円のBasePointに入る(CenterPart/Coordinateではない)。"""
        t = parse_vptw(fixture("VPTW60_active.xml"))
        fcs = [i for i in t["infos"] if i["kind"].startswith("予報")]
        self.assertEqual(len(fcs), 2)
        self.assertEqual(fcs[0]["coord"], "北緯２７．２度東経１３０．９度")
        self.assertEqual(fcs[0]["circle"], "105")
        self.assertEqual(fcs[0]["intensity"], "非常に強い")
        self.assertEqual(fcs[1]["size"], "大型")
        # 数値のない移動速度は電文の文字表現をそのまま保持する
        self.assertEqual(fcs[1]["speed"], "ゆっくり")

    def test_real_dissipated_telegram(self):
        """実電文: 熱帯低気圧化。文字表現(ゆっくり/なし)を落とさない。"""
        t = parse_vptw(fixture("VPTW60_td.xml"))
        self.assertTrue(t["dissipated"])
        self.assertIn("消滅", t["remark"])
        cur = t["infos"][0]
        self.assertEqual(cur["speed"], "ゆっくり")
        self.assertEqual(cur["gale"], "なし")
        self.assertEqual(cur["class"], "熱帯低気圧(TD)")


class TestRenderTyphoon(unittest.TestCase):
    def test_active_page(self):
        t = parse_vptw(fixture("VPTW60_active.xml"))
        html = render_typhoon([t], "08月15日 07:00", "")
        self.assertIn("台風第12号(ノグリー)", html)
        self.assertIn("南大東島の南南東約１６０ｋｍ", html)
        self.assertIn("950hPa", html)
        self.assertIn("中心付近で40m/s", html)
        self.assertIn("全域110km", html)
        self.assertIn("105km", html)  # 予報円の半径
        self.assertIn("ゆっくり", html)  # 数値なしの速度をそのまま表示

    def test_quiet_page_is_still_published(self):
        """台風がなくてもページは常設する(ブックマーク維持)。"""
        html = render_typhoon([], "08月15日 07:00", "")
        self.assertIn("現在、台風は発生していません。", html)
        self.assertIn("台風の強さ・大きさ", html)

    def test_dissipated_is_not_shown_as_active(self):
        t = parse_vptw(fixture("VPTW60_td.xml"))
        html = render_typhoon([t], "08月15日 07:00", "")
        self.assertIn("現在、台風は発生していません。", html)
        self.assertIn("消滅", html)  # 直近の経過は注記する

    def test_index_lists_active_typhoon_only(self):
        active = parse_vptw(fixture("VPTW60_active.xml"))
        gone = parse_vptw(fixture("VPTW60_td.xml"))
        html = render_index([], [], None, [], [active, gone], "08月15日 07:00", "")
        self.assertIn("台風第12号(ノグリー)", html)
        self.assertNotIn("台風第17号", html)
        quiet = render_index([], [], None, [], [gone], "08月15日 07:00", "")
        self.assertIn("台風はありません", quiet)


class TestFeedCutoff(unittest.TestCase):
    def test_utc_feed_vs_jst_cutoff(self):
        """フィードはUTC「Z」表記、cutoffはJST。文字列比較では判定を誤る。"""
        now = datetime.datetime(2026, 8, 15, 17, 0, tzinfo=JST)
        cutoff = now - datetime.timedelta(hours=24)
        self.assertTrue(within("2026-08-14T12:40:28Z", cutoff))  # 21:40 JST=24h以内
        self.assertFalse(within("2026-08-13T12:40:28Z", cutoff))
        self.assertFalse(within("", cutoff))
        # 文字列比較だと誤判定することを示す(修正前の挙動)
        self.assertFalse("2026-08-14T12:40:28Z" >= cutoff.isoformat())


if __name__ == "__main__":
    unittest.main()
