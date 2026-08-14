"""気象警報・注意報(Ｒ０６)電文 VPWW55〜61 の解析。

「新たな防災気象情報」(2026-05-29運用開始)の新体系のみを扱う。
経過措置の旧電文(VPWW53/54, VXWW50等)は購読しない(docs/design.md §8.3)。
コード表は公式解説資料別表3準拠(docs/research/2026-08-14-new-format-research.md)。
"""

from .jmautil import child, child_text, children, first, iter_named, strip_ns, text

WARNING_TYPES = ("VPWW55", "VPWW56", "VPWW57", "VPWW58", "VPWW59", "VPWW60", "VPWW61")

EXPECTED_VERSIONS = {"1.5_0"}

# 新体系では発表されない洪水コード。新電文に現れたら仕様変化とみなし監視通知に乗せる。
LEGACY_FLOOD_CODES = {"04", "18"}

# 発表区域の粒度。市町村をまとめた地域を第一候補とする。
# 電文中のtype属性は全角括弧のため、比較前に_norm()で正規化する。
GRANULARITY_PREFERENCE = (
    "気象警報・注意報(市町村等をまとめた地域等)",
    "気象警報・注意報(一次細分区域等)",
    "気象警報・注意報(府県予報区等)",
)


def _norm(s):
    # 全角括弧(U+FF08/U+FF09)を半角に正規化して比較する
    return (s or "").replace("（", "(").replace("）", ")")


def severity_of(name):
    """警報等の名称から強度区分を返す(5=特別警報, 4=危険警報, 3=警報, 2=注意報)。"""
    if "特別警報" in name:
        return 5
    if "危険警報" in name:
        return 4
    if "注意報" in name:
        return 2
    if "警報" in name:
        return 3
    return 0


def parse_vpwwxx(data):
    """1電文を解析し、区域ごとの発表状況と異常検知結果を返す。"""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(data)
    head = first(root, "Head") or root
    out = {
        "title": text(head, "Title"),
        "report_dt": text(head, "ReportDateTime"),
        "headline": "",
        "version": text(head, "InfoKindVersion"),
        "areas": [],  # [(区域名, [ {name, code, status} ])]
        "anomalies": [],
    }
    hl = first(head, "Headline")
    if hl is not None:
        out["headline"] = text(hl, "Text")

    if out["version"] and out["version"] not in EXPECTED_VERSIONS:
        out["anomalies"].append(f"InfoKindVersion想定外: {out['version']}")

    warnings = {}
    for w in iter_named(root, "Warning"):
        warnings[_norm(w.get("type", ""))] = w
    block = None
    for pref in GRANULARITY_PREFERENCE:
        if _norm(pref) in warnings:
            block = warnings[_norm(pref)]
            break
    if block is None:
        out["anomalies"].append("既知の粒度のWarningブロックなし")
        return out

    for item in children(block, "Item"):
        area = ""
        a = child(item, "Area")
        if a is not None:
            area = child_text(a, "Name")
        kinds = []
        for k in children(item, "Kind"):
            name = child_text(k, "Name")
            code = child_text(k, "Code")
            status = child_text(k, "Status")
            if code in LEGACY_FLOOD_CODES:
                out["anomalies"].append(f"新電文に洪水コード{code}が出現({area})")
            if not name or name in ("解除", "なし") or status == "解除":
                continue
            kinds.append({"name": name, "code": code, "status": status})
        out["areas"].append((area, kinds))
    return out


def merge_office(parses):
    """同一官署の複数電文(大雨・土砂・高潮・…)を区域単位に統合する。

    返り値: {
      areas: [(区域名, [kind,...])]   # 電文出現順・区域は初出順
      max_severity, report_dt(最新), headlines, anomalies
    }
    """
    order = []
    merged = {}
    headlines = []
    anomalies = []
    report_dt = ""
    for p in parses:
        if p["report_dt"] > report_dt:
            report_dt = p["report_dt"]
        if p["headline"]:
            headlines.append((p["report_dt"], p["headline"]))
        anomalies.extend(p["anomalies"])
        for area, kinds in p["areas"]:
            if area not in merged:
                merged[area] = []
                order.append(area)
            known = {k["name"] for k in merged[area]}
            merged[area].extend(k for k in kinds if k["name"] not in known)
    for area in merged:
        merged[area].sort(key=lambda k: -severity_of(k["name"]))
    max_sev = max(
        (severity_of(k["name"]) for ks in merged.values() for k in ks), default=0
    )
    headlines.sort(reverse=True)
    return {
        "areas": [(a, merged[a]) for a in order],
        "max_severity": max_sev,
        "report_dt": report_dt,
        "headlines": [h for _dt, h in headlines],
        "anomalies": anomalies,
    }
