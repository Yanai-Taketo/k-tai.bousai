"""指定河川洪水予報(VXKO50〜76)の解析。

**河川管理者(国土交通省の事務所・都道府県)と気象庁の共同発表**
(電文のPublishingOfficeは例:「仙台河川国道事務所 仙台管区気象台」)。
出典表示を気象庁単独にしないこと。

電文構造は気象警報・注意報と同じ形をしており、Headline/Information の
Item ごとに Kind(レベル名)と Areas(河川・予報区域)が入る。
Information の type で粒度が分かれる:
  「指定河川洪水予報（予報区域）」… 予報区域(例: 名取川)
  「指定河川洪水予報（河川）」    … 河川名
  「指定河川洪水予報（府県予報区等）」… 都道府県

名称は新体系(2026-05-29運用開始)に対応済みで、「レベル２氾濫注意報」
「レベル４氾濫危険警報」等が入る。解除は名称に「解除」が付く。
"""

import xml.etree.ElementTree as ET

from .jmautil import child_text, children, first, iter_named, text

FLOOD_TYPES = ("VXKO50", "VXKO51", "VXKO52", "VXKO70", "VXKO71", "VXKO72",
               "VXKO73", "VXKO74", "VXKO75", "VXKO76")

AREA_INFO = "指定河川洪水予報（予報区域）"
PREF_INFO = "指定河川洪水予報（府県予報区等）"


def _items(head, info_type):
    """指定したInformation配下の (レベル名, [区域名]) を返す。"""
    out = []
    for info in iter_named(head, "Information"):
        if info.get("type") != info_type:
            continue
        for item in children(info, "Item"):
            kind = first(item, "Kind")
            name = child_text(kind, "Name") if kind is not None else ""
            areas = [
                child_text(a, "Name")
                for group in children(item, "Areas")
                for a in children(group, "Area")
                if child_text(a, "Name")
            ]
            if name:
                out.append((name, areas))
    return out


def parse_vxko(data):
    """指定河川洪水予報1電文を解析する。"""
    root = ET.fromstring(data)
    ctrl = first(root, "Control")
    head = first(root, "Head") or root
    hl = first(head, "Headline")
    rivers = _items(head, AREA_INFO)
    prefs = sorted({p for _n, areas in _items(head, PREF_INFO) for p in areas})
    # 解除でない発表が1件でもあれば「発表中」
    active = [(n, a) for n, a in rivers if "解除" not in n]
    return {
        "title": text(head, "Title"),
        "report_dt": text(head, "ReportDateTime"),
        "info_type": text(head, "InfoType"),
        "publisher": text(ctrl, "PublishingOffice") if ctrl is not None else "",
        "headline": text(hl, "Text") if hl is not None else "",
        "rivers": rivers,
        "active": active,
        "prefs": prefs,
    }


def merge_office(parses):
    """同一府県の複数電文を河川単位に統合する(河川ごとに最新の状態を採る)。

    返り値: [(河川名, レベル名)] 発表中のみ。解除された河川は落とす。
    """
    latest = {}
    for p in sorted(parses, key=lambda x: x["report_dt"]):
        for name, areas in p["rivers"]:
            for area in areas or [""]:
                latest[area] = name
    return [(a, n) for a, n in latest.items() if a and "解除" not in n]
