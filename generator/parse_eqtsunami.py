"""地震(VXSE51/VXSE53)・津波(VTSE41)電文の解析。今回の体系整理の対象外・変更なし。"""

import xml.etree.ElementTree as ET

from .jmautil import child_text, first, iter_named, text


def parse_vxse53(data):
    """震源・震度に関する情報。"""
    root = ET.fromstring(data)
    hypo = first(root, "Hypocenter")
    mag = ""
    for e in iter_named(root, "Magnitude"):
        mag = (e.text or "").strip()
        break
    return {
        "kind": "震源・震度",
        "event_id": text(root, "EventID"),
        "origin": text(root, "OriginTime"),
        "hypo": text(hypo, "Name") if hypo is not None else "",
        "mag": mag,
        "maxint": text(root, "MaxInt"),
        "report_dt": text(root, "ReportDateTime"),
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
