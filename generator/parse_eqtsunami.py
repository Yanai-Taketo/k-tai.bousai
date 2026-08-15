"""地震(VXSE51/VXSE53)・津波(VTSE41)電文の解析。

震度は電文の値(1〜4, 5-, 5+, 6-, 6+, 7)をそのまま保持し、表示時に
気象庁の表記(５弱・６強等)へ変換する(INT_LABEL)。
"""

import xml.etree.ElementTree as ET

from .jmautil import child_text, children, first, iter_named, text

# 震度の強い順。電文値→表示名。
INT_ORDER = ("7", "6+", "6-", "5+", "5-", "4", "3", "2", "1")
INT_LABEL = {
    "7": "７",
    "6+": "６強",
    "6-": "６弱",
    "5+": "５強",
    "5-": "５弱",
    "4": "４",
    "3": "３",
    "2": "２",
    "1": "１",
}


def int_label(value):
    """震度の電文値を表示名にする。未知の値はそのまま返す(仕様変化に耐える)。"""
    return INT_LABEL.get((value or "").strip(), (value or "").strip())


def int_rank(value):
    """震度の強い順に並べるためのキー(大きいほど強い)。"""
    v = (value or "").strip()
    return len(INT_ORDER) - INT_ORDER.index(v) if v in INT_ORDER else -1


def _observation_tree(root):
    """Observation配下を [{int, pref, area, city}] に平坦化する。

    City階層が無い電文(震度速報等)ではcityを空にし、Areaを最小粒度とする。
    """
    obs = first(root, "Observation")
    if obs is None:
        return []
    rows = []
    for pref in children(obs, "Pref"):
        pname = child_text(pref, "Name")
        areas = children(pref, "Area")
        if not areas:
            rows.append(
                {"int": child_text(pref, "MaxInt"), "pref": pname, "area": "", "city": ""}
            )
            continue
        for area in areas:
            aname = child_text(area, "Name")
            cities = children(area, "City")
            if not cities:
                rows.append(
                    {"int": child_text(area, "MaxInt"), "pref": pname, "area": aname, "city": ""}
                )
                continue
            for city in cities:
                rows.append(
                    {
                        "int": child_text(city, "MaxInt"),
                        "pref": pname,
                        "area": aname,
                        "city": child_text(city, "Name"),
                    }
                )
    return rows


def _comments(root):
    """固定付加文(津波の有無等)を出現順に返す。観測点注記(0262)は表示しないので除く。"""
    out = []
    for tag in ("ForecastComment", "VarComment", "FreeFormComment"):
        for c in iter_named(root, tag):
            t = child_text(c, "Text")
            code = child_text(c, "Code")
            if t and code != "0262":
                out.append(t)
    return out


def _hypo_parts(hypo):
    """震央要素から (座標表現, 深さ表現) を取り出す。

    Coordinateのdescriptionは「北緯４０．２度　東経１４２．９度　深さ　２０ｋｍ」の形。
    深さが「ごく浅い」等の文字列のこともあるため、分割して原文のまま扱う。
    """
    if hypo is None:
        return "", ""
    desc = ""
    for e in iter_named(hypo, "Coordinate"):
        desc = (e.get("description") or "").strip()
        if desc:
            break
    if not desc:
        return "", ""
    if "深さ" in desc:
        coord, depth = desc.split("深さ", 1)
        return coord.strip(), depth.strip()
    return desc, ""


def parse_vxse53(data):
    """震源・震度に関する情報。"""
    root = ET.fromstring(data)
    hypo = first(root, "Hypocenter")
    mag = ""
    for e in iter_named(root, "Magnitude"):
        mag = (e.text or "").strip()
        break
    coord, depth = _hypo_parts(hypo)
    detail_name = text(hypo, "DetailedName") if hypo is not None else ""
    return {
        "kind": "震源・震度",
        "event_id": text(root, "EventID"),
        "origin": text(root, "OriginTime"),
        "hypo": text(hypo, "Name") if hypo is not None else "",
        "detail_name": detail_name,
        "mag": mag,
        "maxint": text(root, "MaxInt"),
        "report_dt": text(root, "ReportDateTime"),
        "headline": text(first(root, "Headline"), "Text") if first(root, "Headline") else "",
        "coord": coord,
        "depth": depth,
        "comments": _comments(root),
        "obs": _observation_tree(root),
    }


def parse_vxse51(data):
    """震度速報(震源情報が出る前の第一報)。"""
    root = ET.fromstring(data)
    areas = []
    for pref in iter_named(root, "Pref"):
        name = child_text(pref, "Name")
        if name:
            areas.append(name)
        if len(areas) >= 4:
            break
    return {
        "kind": "震度速報",
        "event_id": text(root, "EventID"),
        "origin": text(root, "TargetDateTime"),
        "hypo": "、".join(areas),
        "mag": "",
        "maxint": text(root, "MaxInt"),
        "report_dt": text(root, "ReportDateTime"),
        "headline": text(first(root, "Headline"), "Text") if first(root, "Headline") else "",
        "detail_name": "",
        "coord": "",
        "depth": "",
        "comments": _comments(root),
        "obs": _observation_tree(root),
    }


def parse_vtse41(data):
    """津波警報・注意報・予報。Headlineの津波予報領域表現から現況を組み立てる。"""
    root = ET.fromstring(data)
    head = first(root, "Head") or root
    info_type = text(head, "InfoType")
    hl = first(head, "Headline")
    items = []
    if hl is not None:
        for item in iter_named(hl, "Item"):
            kind = first(item, "Kind")
            kname = child_text(kind, "Name") if kind is not None else ""
            anames = [
                child_text(a, "Name")
                for a in iter_named(item, "Area")
                if child_text(a, "Name")
            ]
            if kname:
                items.append({"kind": kname, "areas": anames})
    active = info_type != "取消" and any(
        ("警報" in i["kind"] or "注意報" in i["kind"]) and "解除" not in i["kind"]
        for i in items
    )
    return {
        "report_dt": text(head, "ReportDateTime"),
        "info_type": info_type,
        "headline": text(hl, "Text") if hl is not None else "",
        "items": items,
        "active": active,
    }
