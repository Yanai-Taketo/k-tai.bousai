"""熱中症警戒アラート(VPFT50)と指定河川洪水予報(VXKO)のテスト。

どちらも**気象庁単独ではない共同発表**であり、出典表示を誤ると事実誤認になる:
  熱中症警戒アラート … 環境省 + 気象庁
  指定河川洪水予報   … 河川管理者(国交省の事務所・都道府県) + 気象庁
"""

import datetime
import os
import unittest

from generator.jmautil import JST
from generator.parse_flood import merge_office as merge_flood, parse_vxko
from generator.parse_heat import PUBLISHER, is_current, parse_vpft50
from generator.render import render_pref

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(FIX, name), "rb") as f:
        return f.read()


class TestHeatAlert(unittest.TestCase):
    def test_parse_real_telegram(self):
        a = parse_vpft50(fixture("VPFT50_wakayama.xml"))
        self.assertEqual(a["title"], "和歌山県熱中症警戒アラート")
        self.assertFalse(a["cancelled"])
        self.assertTrue(a["lead"].startswith("和歌山県では、明日"))
        self.assertIn("熱中症予防のための行動をとってください。", a["lead"])
        self.assertEqual(a["temps"], "和歌山３１度、潮岬２９度")

    def test_lead_only_not_whole_body(self):
        """本文は1,400字超。ページ予算に収まるよう冒頭の要旨だけを採る。"""
        a = parse_vpft50(fixture("VPFT50_wakayama.xml"))
        self.assertLess(len(a["lead"]), 200)
        # 汎用の行動指針や指標の説明は含めない
        self.assertNotIn("ＷＢＧＴ", a["lead"])
        self.assertNotIn("エアコン", a["lead"])

    def test_expires_after_target_day(self):
        """前日17時発表は対象日いっぱい有効、翌々日は無効。"""
        a = parse_vpft50(fixture("VPFT50_wakayama.xml"))  # 対象日=8/16
        self.assertTrue(is_current(a, datetime.datetime(2026, 8, 15, 18, tzinfo=JST)))
        self.assertTrue(is_current(a, datetime.datetime(2026, 8, 16, 23, tzinfo=JST)))
        self.assertFalse(is_current(a, datetime.datetime(2026, 8, 17, 9, tzinfo=JST)))

    def test_cancelled_is_not_current(self):
        a = parse_vpft50(fixture("VPFT50_wakayama.xml"))
        a["cancelled"] = True
        self.assertFalse(is_current(a, datetime.datetime(2026, 8, 15, 18, tzinfo=JST)))

    def test_publisher_is_joint(self):
        self.assertEqual(PUBLISHER, "環境省・気象庁")


class TestFloodForecast(unittest.TestCase):
    def test_parse_active(self):
        p = parse_vxko(fixture("VXKO51_active.xml"))
        self.assertEqual(p["rivers"], [("レベル４氾濫危険警報", ["名取川"])])
        self.assertTrue(p["active"])
        self.assertEqual(p["prefs"], ["宮城県"])
        self.assertIn("氾濫危険水位", p["headline"])

    def test_publisher_is_joint_and_varies(self):
        """発表主体は河川管理者により異なる(国の事務所・都道府県)。"""
        self.assertEqual(
            parse_vxko(fixture("VXKO51_natorigawa.xml"))["publisher"],
            "仙台河川国道事務所 仙台管区気象台",
        )
        self.assertEqual(
            parse_vxko(fixture("VXKO76_zenpukuji.xml"))["publisher"], "東京都 気象庁"
        )

    def test_cancelled_river_is_dropped(self):
        """解除された河川は一覧に残さない。"""
        self.assertEqual(merge_flood([parse_vxko(fixture("VXKO51_natorigawa.xml"))]), [])

    def test_later_telegram_wins(self):
        """同じ河川は発表時刻の新しい方を採る(発表→解除で消える)。"""
        active = parse_vxko(fixture("VXKO51_active.xml"))
        cancel = parse_vxko(fixture("VXKO51_natorigawa.xml"))
        active["report_dt"] = "2026-08-14T05:00:00+09:00"
        cancel["report_dt"] = "2026-08-14T06:30:00+09:00"
        self.assertEqual(merge_flood([active, cancel]), [])
        # 逆順(解除の後に再発表)なら残る
        cancel["report_dt"] = "2026-08-14T04:00:00+09:00"
        self.assertEqual(
            merge_flood([cancel, active]), [("名取川", "レベル４氾濫危険警報")]
        )


class TestPrefPageIntegration(unittest.TestCase):
    def _render(self, floods=None, heat=None):
        return render_pref(
            "宮城県", None, [], None, None, floods, heat, "08月15日 12:00", ""
        )

    def test_flood_section_shows_river_and_joint_publisher(self):
        p = parse_vxko(fixture("VXKO51_active.xml"))
        floods = {
            "rivers": merge_flood([p]),
            "report_dt": p["report_dt"],
            "publisher": p["publisher"],
            "headline": p["headline"],
        }
        html = self._render(floods=floods)
        self.assertIn("指定河川の洪水予報", html)
        self.assertIn("名取川", html)
        self.assertIn("レベル４氾濫危険警報", html)
        # 共同発表であることが分かる表示になっている
        self.assertIn("仙台河川国道事務所 仙台管区気象台", html)

    def test_heat_section_shows_env_ministry(self):
        a = parse_vpft50(fixture("VPFT50_wakayama.xml"))
        html = self._render(heat=a)
        self.assertIn("和歌山県熱中症警戒アラート", html)
        self.assertIn("環境省・気象庁", html)
        self.assertIn("予想最高気温", html)

    def test_sections_absent_when_no_data(self):
        html = self._render()
        self.assertNotIn("指定河川の洪水予報", html)
        self.assertNotIn("熱中症警戒アラート", html)


if __name__ == "__main__":
    unittest.main()
