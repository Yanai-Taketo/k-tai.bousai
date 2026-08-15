"""地震詳細ページ(各地の震度)の生成テスト。

巨大地震では市町村単位の観測が数千件に達しページ予算(gzip 6KB)を超えるため、
粒度を市町村→地域→都道府県へ段階的に落とす。この分岐は実データでは滅多に
発生しない(=普段のテストで守られない)一方、発生する時こそサイトが必要とされる
場面なので、合成電文で明示的に検証する。
"""

import gzip
import os
import re
import unittest

from generator.parse_eqtsunami import int_label, int_rank, parse_vxse51, parse_vxse53
from generator.render import (
    EQ_GZIP_BUDGET,
    eq_detail_href,
    eq_detail_rel,
    minify,
    render_eq,
    render_eq_detail,
)

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(FIX, name), "rb") as f:
        return f.read()


def gz_size(html):
    return len(gzip.compress(minify(html).encode("utf-8"), 9))


def synth_quake(n_pref=40, n_area=8, n_city=6):
    """巨大地震を模した合成電文(既定で1,920市町村。東日本大震災級を想定)。"""
    ints = ["7", "6+", "6-", "5+", "5-", "4", "3", "2", "1"]
    prefs, k = [], 0
    for p in range(n_pref):
        areas = []
        for a in range(n_area):
            cities = []
            for c in range(n_city):
                v = ints[k % len(ints)]
                cities.append(
                    f"<City><Name>市町村名{p:02d}{a}{c}</Name>"
                    f"<Code>{k:07d}</Code><MaxInt>{v}</MaxInt></City>"
                )
                k += 1
            areas.append(
                f"<Area><Name>細分区域{p:02d}{a}</Name><Code>{p}{a}</Code>"
                f"<MaxInt>7</MaxInt>{''.join(cities)}</Area>"
            )
        prefs.append(
            f"<Pref><Name>都道府県{p:02d}</Name><Code>{p:02d}</Code>"
            f"<MaxInt>7</MaxInt>{''.join(areas)}</Pref>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Report xmlns="http://xml.kishou.go.jp/jmaxml1/"'
        ' xmlns:jmx_eb="http://xml.kishou.go.jp/jmaxml1/elementBasis1/">'
        "<Head><ReportDateTime>2026-08-15T12:00:00+09:00</ReportDateTime>"
        "<EventID>99999999999999</EventID>"
        "<Headline><Text>１５日１２時００分ころ、地震がありました。</Text></Headline></Head>"
        "<Body><Earthquake><OriginTime>2026-08-15T12:00:00+09:00</OriginTime>"
        "<Hypocenter><Area><Name>三陸沖</Name>"
        '<jmx_eb:Coordinate description="北緯３８．０度　東経１４２．０度　深さ　２４ｋｍ">'
        "+38.0+142.0-24000/</jmx_eb:Coordinate></Area></Hypocenter>"
        '<jmx_eb:Magnitude type="Mj">9.0</jmx_eb:Magnitude></Earthquake>'
        f"<Intensity><Observation><MaxInt>7</MaxInt>{''.join(prefs)}</Observation></Intensity>"
        '<Comments><ForecastComment codeType="固定付加文">'
        "<Text>この地震による津波の心配はありません。</Text><Code>0215</Code>"
        "</ForecastComment></Comments></Body></Report>"
    ).encode("utf-8")


class TestIntensityScale(unittest.TestCase):
    def test_labels(self):
        """電文値を気象庁表記に変換する(5-→５弱)。未知の値はそのまま通す。"""
        self.assertEqual(int_label("5-"), "５弱")
        self.assertEqual(int_label("6+"), "６強")
        self.assertEqual(int_label("7"), "７")
        self.assertEqual(int_label("不明"), "不明")

    def test_order_is_descending_by_strength(self):
        got = sorted(["3", "5+", "1", "6-", "7", "5-"], key=int_rank, reverse=True)
        self.assertEqual(got, ["7", "6-", "5+", "5-", "3", "1"])


class TestEqDetailRealTelegram(unittest.TestCase):
    def test_vxse53_extracts_detail(self):
        """実電文から深さ・見出し文・固定付加文・市町村震度を取り出す。"""
        q = parse_vxse53(fixture("VXSE53_sample.xml"))
        self.assertEqual(q["depth"], "２０ｋｍ")
        self.assertIn("北緯", q["coord"])
        self.assertIn("地震がありました", q["headline"])
        self.assertIn("この地震による津波の心配はありません。", q["comments"])
        # 観測点注記(0262)は表示対象外
        self.assertFalse(any("＊印" in c for c in q["comments"]))
        self.assertTrue(q["obs"])
        self.assertEqual(q["obs"][0]["city"], "八戸市")

    def test_vxse51_area_granularity(self):
        """震度速報は市町村階層を持たないため、地域が最小粒度になる。"""
        q = parse_vxse51(fixture("VXSE51_sample.xml"))
        self.assertTrue(q["obs"])
        self.assertTrue(all(r["city"] == "" for r in q["obs"]))
        self.assertTrue(all(r["area"] for r in q["obs"]))

    def test_detail_page_renders_city_names(self):
        q = parse_vxse53(fixture("VXSE53_sample.xml"))
        html = render_eq_detail(q, "08月15日 12:00", "")
        self.assertIn("市町村単位", html)
        self.assertIn("八戸市", html)
        self.assertIn("震度１", html)
        self.assertLessEqual(gz_size(html), EQ_GZIP_BUDGET)

    def test_detail_paths_and_links(self):
        """出力はフラットな.html、内部リンクは拡張子なし。

        実測(2026-08-15): Cloudflare Pages・GitHub Pages とも拡張子なしURLを
        0リダイレクトで配信する。`.html`付き・末尾スラッシュ付きはCloudflareが
        308を返し1往復増える。
        """
        q = parse_vxse53(fixture("VXSE53_sample.xml"))
        self.assertEqual(eq_detail_rel(q), "eq/20260814224256.html")
        self.assertEqual(eq_detail_href(q), "eq/20260814224256")
        self.assertIsNone(eq_detail_rel({"event_id": ""}))
        self.assertIsNone(eq_detail_href({"event_id": ""}))
        # パス名に使えない文字は除去する(パストラバーサル防止)
        self.assertEqual(
            eq_detail_rel({"event_id": "../../etc/passwd"}), "eq/etcpasswd.html"
        )

    def test_no_html_suffix_links_anywhere(self):
        """内部リンクに .html を残さない(Cloudflareの308を避けるため)。"""
        q = parse_vxse53(fixture("VXSE53_sample.xml"))
        html = render_eq_detail(q, "08月15日 12:00", "")
        internal = [
            h for h in re.findall(r'href="([^"]+)"', html) if not h.startswith("http")
        ]
        self.assertTrue(internal)
        self.assertEqual([h for h in internal if h.endswith(".html")], [])


class TestNoIntensity(unittest.TestCase):
    def test_absent_intensity_is_not_called_pending(self):
        """震度が電文に無い場合に「調査中」と断定しない。

        遠地地震(例: インドネシア付近M7.7)は国内で震度を観測しないためMaxIntが
        無い。これを「調査中」と表示すると、後から震度が出るかのように誤解させる。
        """
        q = parse_vxse53(fixture("VXSE53_sample.xml"))
        q["maxint"] = ""
        q["obs"] = []
        html = render_eq_detail(q, "08月15日 12:00", "")
        self.assertIn("国内での震度の発表はありません", html)
        self.assertNotIn("調査中", html)

    def test_list_shows_dash(self):
        q = parse_vxse53(fixture("VXSE53_sample.xml"))
        q["maxint"] = ""
        html = render_eq([q], "08月15日 12:00", "")
        self.assertNotIn("調査中", html)


class TestEqDetailHugeQuake(unittest.TestCase):
    def test_falls_back_to_area_and_stays_in_budget(self):
        """1,920市町村の巨大地震でも予算内に収まり、縮約した旨を明示する。"""
        q = parse_vxse53(synth_quake())
        self.assertEqual(len(q["obs"]), 1920)
        html = render_eq_detail(q, "08月15日 12:05", "")
        self.assertLessEqual(gz_size(html), EQ_GZIP_BUDGET)
        self.assertIn("各地の震度(地域単位", html)
        self.assertIn("省略して表示", html)

    def test_strongest_intensity_comes_first(self):
        """最も強い震度が先頭に来る(避難判断に直結するため順序は要件)。"""
        q = parse_vxse53(synth_quake())
        html = render_eq_detail(q, "08月15日 12:05", "")
        order = re.findall(r"<strong>震度([^<]+)</strong>", html)
        self.assertTrue(order)
        self.assertEqual(order[0], "７")
        ranks = [int_rank(v) for v in ("7", "6+", "6-", "5+", "5-", "4", "3", "2", "1")]
        labels = {int_label(v): r for v, r in zip(
            ("7", "6+", "6-", "5+", "5-", "4", "3", "2", "1"), ranks)}
        seen = [labels[o] for o in order if o in labels]
        self.assertEqual(seen, sorted(seen, reverse=True))

    def test_pref_fallback_when_even_area_is_too_large(self):
        """地域単位でも収まらない極端な場合は都道府県単位まで落とす。"""
        q = parse_vxse53(synth_quake(n_pref=47, n_area=60, n_city=2))
        html = render_eq_detail(q, "08月15日 12:05", "")
        self.assertLessEqual(gz_size(html), EQ_GZIP_BUDGET)
        self.assertIn("各地の震度(都道府県単位", html)


if __name__ == "__main__":
    unittest.main()
