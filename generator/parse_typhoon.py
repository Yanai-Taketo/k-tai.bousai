"""台風解析・予報情報(VPTW60〜65)の解析。

電文構成(公式解説資料「台風解析・予報情報電文(新形式)」準拠):
  Head: EventID(TC番号)・Serial(情報番号)・InfoType
  Body/MeteorologicalInfos type="台風情報"
    MeteorologicalInfo が「実況」「推定 N時間後」「予報 N時間後」の順に並ぶ
      Kind/Property/Type=呼称 → TyphoonNamePart(名前・番号・消滅等のRemark)
      Kind/Property/Type=階級 → ClassPart(熱帯擾乱種類・大きさ階級・強さ階級)
      Kind/Property/Type=中心 → CenterPart(中心位置・存在地域・進行方向・速度・
                                中心気圧、予報時は ProbabilityCircle=予報円)
      Kind/Property/Type=風   → WindPart(最大風速・最大瞬間風速)
      Area → Circle type="暴風域"/"強風域"(方向+半径)

数値が無く文字表現だけの場合がある(速度「ゆっくり」「ほとんど停滞」、半径「なし」、
方向「全域」)。これらは電文上の正規の値なので、欄を消さず description をそのまま出す。
"""

import xml.etree.ElementTree as ET

from .jmautil import child_text, children, first, iter_named, strip_ns, text

TYPHOON_TYPES = ("VPTW60", "VPTW61", "VPTW62", "VPTW63", "VPTW64", "VPTW65")


def _by_type(elem, tag, type_value):
    """type属性が一致する最初の要素を返す(Coordinate 度/度分、Speed ノット/km/h の選別用)。"""
    if elem is None:
        return None
    for e in iter_named(elem, tag):
        if e.get("type") == type_value:
            return e
    return None


def _val(e):
    """要素の表示値。数値本体があればそれ、無ければ description(「ゆっくり」等)。"""
    if e is None:
        return ""
    body = (e.text or "").strip()
    return body or (e.get("description") or e.get("condition") or "").strip()


def _desc(e):
    """人が読む表現を優先する(Coordinateは本文が機械可読形式のため)。"""
    if e is None:
        return ""
    return (e.get("description") or "").strip() or (e.text or "").strip()


def _unit_val(elem, tag, type_value, unit):
    """type属性とunit属性の両方で絞り込む(km/h と ノット の区別など)。"""
    if elem is None:
        return None
    for e in iter_named(elem, tag):
        if e.get("type") == type_value and e.get("unit") == unit:
            return e
    return None


def _circle(area, kind):
    """暴風域・強風域の表現。「東側300km 西側200km」または「全域110km」「なし」。"""
    for c in iter_named(area, "Circle"):
        if c.get("type") != kind:
            continue
        parts = []
        for axis in iter_named(c, "Axis"):
            d = first(axis, "Direction")
            r = _unit_val(axis, "Radius", "半径", "km")
            dtxt = _val(d)
            rtxt = _val(r)
            if not rtxt:
                continue
            if rtxt == "なし":
                return "なし"
            parts.append(f"{dtxt}{rtxt}km" if dtxt and dtxt != "全域" else f"全域{rtxt}km")
        return " ".join(parts)
    return ""


def _property(item, type_value):
    """Item配下から Kind/Property/Type が一致する Property を返す。"""
    for kind in children(item, "Kind"):
        for prop in children(kind, "Property"):
            if child_text(prop, "Type") == type_value:
                return prop
    return None


def _one_info(info):
    """MeteorologicalInfo 1件を辞書化する。"""
    dt_el = first(info, "DateTime")
    out = {
        "kind": (dt_el.get("type") if dt_el is not None else "") or "",
        "dt": (dt_el.text or "").strip() if dt_el is not None else "",
        "class": "", "size": "", "intensity": "",
        "location": "", "coord": "", "direction": "", "speed": "",
        "pressure": "", "wind_max": "", "wind_gust": "",
        "storm": "", "gale": "", "circle": "",
    }
    item = first(info, "Item")
    if item is None:
        return out

    cls = _property(item, "階級")
    if cls is not None:
        out["class"] = _val(_by_type(cls, "TyphoonClass", "熱帯擾乱種類"))
        out["size"] = _val(_by_type(cls, "AreaClass", "大きさ階級"))
        out["intensity"] = _val(_by_type(cls, "IntensityClass", "強さ階級"))

    ctr = _property(item, "中心")
    if ctr is not None:
        out["coord"] = _desc(_by_type(ctr, "Coordinate", "中心位置（度）"))
        out["location"] = text(ctr, "Location")
        out["direction"] = _val(_by_type(ctr, "Direction", "移動方向"))
        out["speed"] = _val(_unit_val(ctr, "Speed", "移動速度", "km/h"))
        out["pressure"] = _val(_by_type(ctr, "Pressure", "中心気圧"))
        pc = first(ctr, "ProbabilityCircle")
        if pc is not None:
            # 予報では中心位置がCenterPart/CoordinateでなくProbabilityCircle/BasePointに入る
            if not out["coord"]:
                out["coord"] = _desc(_by_type(pc, "BasePoint", "中心位置（度）"))
            for axis in iter_named(pc, "Axis"):
                r = _unit_val(axis, "Radius", "半径", "km")
                if _val(r):
                    out["circle"] = _val(r)
                    break

    wind = _property(item, "風")
    if wind is not None:
        out["wind_max"] = _val(_unit_val(wind, "WindSpeed", "最大風速", "m/s"))
        out["wind_gust"] = _val(_unit_val(wind, "WindSpeed", "最大瞬間風速", "m/s"))

    for area in children(item, "Area"):
        out["storm"] = out["storm"] or _circle(area, "暴風域")
        out["gale"] = out["gale"] or _circle(area, "強風域")
    return out


def parse_vptw(data):
    """台風解析・予報情報1電文を解析する。"""
    root = ET.fromstring(data)
    head = first(root, "Head") or root
    name_part = first(root, "TyphoonNamePart")
    infos = [_one_info(i) for i in iter_named(root, "MeteorologicalInfo")]
    return {
        "event_id": text(head, "EventID"),
        "report_dt": text(head, "ReportDateTime"),
        "info_type": text(head, "InfoType"),
        "serial": text(head, "Serial"),
        "name": child_text(name_part, "Name") if name_part is not None else "",
        "name_kana": child_text(name_part, "NameKana") if name_part is not None else "",
        "number": child_text(name_part, "Number") if name_part is not None else "",
        "remark": child_text(name_part, "Remark") if name_part is not None else "",
        "infos": infos,
        # 「台風消滅」等が入っていれば掲載対象から外す判断に使う
        "dissipated": "消滅" in (child_text(name_part, "Remark") if name_part is not None else ""),
    }


def display_name(t):
    """「台風第20号(ノグリー)」のような見出し。番号が無ければ熱帯低気圧扱い。"""
    num = (t.get("number") or "").strip()
    if num and len(num) >= 4:
        n = num[2:].lstrip("0") or num[2:]
        base = f"台風第{n}号"
    elif num:
        base = f"台風第{num}号"
    else:
        return "熱帯低気圧"
    kana = (t.get("name_kana") or "").strip()
    return f"{base}({kana})" if kana else base
