"""気象防災速報の解析(VPBS50=府県気象防災速報、VPHW50/51=竜巻注意・竜巻目撃)。

決定#16によりフェーズ1スコープ。速報型のため直近24時間分のみ表示する。
旧・記録的短時間大雨情報(VPOA50)は経過措置電文のため購読しない。
"""

import xml.etree.ElementTree as ET

from .jmautil import first, text

SOKUHO_TYPES = ("VPBS50", "VPHW50", "VPHW51")


def parse_sokuho(data):
    """速報電文から見出し情報を取り出す。titleは例: 千葉県気象防災速報(線状降水帯発生)。"""
    root = ET.fromstring(data)
    head = first(root, "Head") or root
    hl = first(head, "Headline")
    return {
        "title": text(head, "Title"),
        "report_dt": text(head, "ReportDateTime"),
        "text": text(hl, "Text") if hl is not None else "",
    }
