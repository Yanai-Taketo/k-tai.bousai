"""府県天気予報(VPFD51)・府県週間天気予報(VPFW50)の解析。

いずれも2026年の体系整理では変更なし(解説資料は令和2年10月1日版)。
表示は「区域ごとの天気文+降水確率」「代表地点の気温」「週間の天気・降水確率」に絞る。
"""

import xml.etree.ElementTree as ET

from .jmautil import child, child_text, children, iter_named, parse_dt, text, JST


def _norm(s):
    # 全角括弧(U+FF08/U+FF09)を半角に正規化して比較する
    return (s or "").replace("（", "(").replace("）", ")")


def _time_defines(tsi):
    """TimeSeriesInfoのTimeDefineを timeId -> (Name, DateTime) で返す。"""
    out = {}
    for td in iter_named(tsi, "TimeDefine"):
        out[td.get("timeId", "")] = (child_text(td, "Name"), child_text(td, "DateTime"))
    return out


def _label(td, ref_id):
    name, iso = td.get(ref_id, ("", ""))
    if name:
        return name
    dt = parse_dt(iso)
    if dt:
        d = dt.astimezone(JST)
        return f"{d.day}日{d.hour}時"
    return ref_id


def parse_vpfd51(data):
    """府県天気予報: 区域ごとの天気・降水確率と、地点の気温。"""
    root = ET.fromstring(data)
    out = {
        "report_dt": text(root, "ReportDateTime"),
        "areas": [],  # {name, weathers:[(時名, 天気)], pops:[(時名, %)]}
        "stations": [],  # {name, temps:[(種別, 度)]}
    }
    by_area = {}
    order = []
    for infos in iter_named(root, "MeteorologicalInfos"):
        kind_type = _norm(infos.get("type", ""))
        if kind_type == "区域予報":
            for tsi in children(infos, "TimeSeriesInfo"):
                td = _time_defines(tsi)
                for item in children(tsi, "Item"):
                    a = child(item, "Area")
                    aname = child_text(a, "Name") if a is not None else ""
                    if not aname:
                        continue
                    if aname not in by_area:
                        by_area[aname] = {"name": aname, "weathers": [], "pops": []}
                        order.append(aname)
                    rec = by_area[aname]
                    for prop in iter_named(item, "Property"):
                        ptype = child_text(prop, "Type")
                        if ptype == "天気" and not rec["weathers"]:
                            # WeatherPart(要約天気)のみ使用。DetailForecast内のWeatherは拾わない
                            wp = next(iter_named(prop, "WeatherPart"), None)
                            if wp is not None:
                                for w in iter_named(wp, "Weather"):
                                    rec["weathers"].append(
                                        (_label(td, w.get("refID", "")), (w.text or "").strip())
                                    )
                        elif ptype == "降水確率" and not rec["pops"]:
                            for p in iter_named(prop, "ProbabilityOfPrecipitation"):
                                rec["pops"].append(
                                    (_label(td, p.get("refID", "")), (p.text or "").strip())
                                )
        elif kind_type == "地点予報":
            for tsi in children(infos, "TimeSeriesInfo"):
                for item in children(tsi, "Item"):
                    st = child(item, "Station")
                    sname = child_text(st, "Name") if st is not None else ""
                    if not sname:
                        continue
                    temps = []
                    for t in iter_named(item, "Temperature"):
                        temps.append((t.get("type", ""), (t.text or "").strip()))
                    if temps:
                        out["stations"].append({"name": sname, "temps": temps})
    out["areas"] = [by_area[a] for a in order]
    return out


def parse_vpfw50(data):
    """府県週間天気予報: 区域ごとの日別天気・降水確率と、地点の最低/最高気温。"""
    root = ET.fromstring(data)
    out = {
        "report_dt": text(root, "ReportDateTime"),
        "areas": [],  # {name, days:[(日付ISO, 天気, 降水確率)]}
        "stations": [],  # {name, days:[(日付ISO, 最低, 最高)]}
    }
    for infos in iter_named(root, "MeteorologicalInfos"):
        kind_type = _norm(infos.get("type", ""))
        for tsi in children(infos, "TimeSeriesInfo"):
            td = _time_defines(tsi)
            dates = {k: v[1] for k, v in td.items()}
            for item in children(tsi, "Item"):
                if kind_type == "区域予報":
                    a = child(item, "Area")
                    aname = child_text(a, "Name") if a is not None else ""
                    if not aname:
                        continue
                    weathers, pops = {}, {}
                    for prop in iter_named(item, "Property"):
                        ptype = child_text(prop, "Type")
                        if ptype == "天気":
                            for w in iter_named(prop, "Weather"):
                                weathers[w.get("refID", "")] = (w.text or "").strip()
                        elif ptype == "降水確率":
                            for p in iter_named(prop, "ProbabilityOfPrecipitation"):
                                pops[p.get("refID", "")] = (p.text or "").strip()
                    if weathers:
                        days = [
                            (dates.get(r, ""), weathers.get(r, ""), pops.get(r, ""))
                            for r in sorted(weathers, key=int)
                        ]
                        out["areas"].append({"name": aname, "days": days})
                elif kind_type == "地点予報":
                    st = child(item, "Station")
                    sname = child_text(st, "Name") if st is not None else ""
                    if not sname:
                        continue
                    lows, highs = {}, {}
                    for t in iter_named(item, "Temperature"):
                        ttype = t.get("type", "")
                        ref = t.get("refID", "")
                        if "最低" in ttype:
                            lows[ref] = (t.text or "").strip()
                        elif "最高" in ttype:
                            highs[ref] = (t.text or "").strip()
                    refs = sorted(set(lows) | set(highs), key=lambda r: int(r or 0))
                    if refs:
                        out["stations"].append(
                            {
                                "name": sname,
                                "days": [
                                    (dates.get(r, ""), lows.get(r, ""), highs.get(r, ""))
                                    for r in refs
                                ],
                            }
                        )
    return out
