"""熱中症警戒アラート(VPFT50)の解析。

**環境省と気象庁の共同発表**(電文のPublishingOfficeは「環境省 気象庁」)。
出典表示を気象庁単独にしないこと。

電文は「同一現象用平文情報」で、本文が1,400字を超える。全文はページ予算に
収まらないため、冒頭の要旨段落と予想最高気温だけを原文のまま抜き出す
(要約・言い換えはしない)。
"""

import re
import xml.etree.ElementTree as ET

from .jmautil import first, parse_dt, text

HEAT_TYPES = ("VPFT50",)

PUBLISHER = "環境省・気象庁"


def _lead_and_temps(body_text):
    """本文から (冒頭の要旨, 予想最高気温) を原文のまま取り出す。"""
    if not body_text:
        return "", ""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body_text) if b.strip()]
    lead = blocks[0] if blocks else ""
    temps = ""
    for i, b in enumerate(blocks):
        if b.startswith("［") and "予想最高気温" in b:
            # 見出し行と数値行が同じブロックにも別ブロックにもなり得る
            parts = b.split("]\n") if "]\n" in b else b.split("］\n")
            temps = parts[1].strip() if len(parts) > 1 else (
                blocks[i + 1].strip() if i + 1 < len(blocks) else ""
            )
            break
    return lead, temps


def parse_vpft50(data):
    """熱中症警戒アラート1電文を解析する。"""
    root = ET.fromstring(data)
    head = first(root, "Head") or root
    body_text = ""
    for c in root.iter():
        if c.tag.rsplit("}", 1)[-1] == "Text" and (c.get("type") == "本文"):
            body_text = (c.text or "").strip()
            break
    lead, temps = _lead_and_temps(body_text)
    info_type = text(head, "InfoType")
    return {
        "title": text(head, "Title"),
        "report_dt": text(head, "ReportDateTime"),
        "target_dt": text(head, "TargetDateTime"),
        "info_type": info_type,
        "lead": lead,
        "temps": temps,
        "cancelled": info_type == "取消",
    }


def is_current(alert, now):
    """対象日が過ぎていないか。前日17時発表は翌日いっぱい有効とみなす。"""
    if alert["cancelled"]:
        return False
    t = parse_dt(alert["target_dt"])
    if t is None:
        return True
    return t.astimezone(now.tzinfo).date() >= now.date()
