"""XML電文の共通ユーティリティ(名前空間非依存の要素アクセス・日時整形)。"""

import datetime

JST = datetime.timezone(datetime.timedelta(hours=9))


def strip_ns(tag):
    return tag.rsplit("}", 1)[-1]


def iter_named(elem, name):
    for e in elem.iter():
        if strip_ns(e.tag) == name:
            yield e


def first(elem, name):
    return next(iter_named(elem, name), None)


def text(elem, name, default=""):
    e = first(elem, name)
    if e is None:
        return default
    return (e.text or default).strip()


def children(elem, name):
    return [c for c in list(elem) if strip_ns(c.tag) == name]


def child(elem, name):
    cs = children(elem, name)
    return cs[0] if cs else None


def child_text(elem, name, default=""):
    c = child(elem, name)
    if c is None:
        return default
    return (c.text or default).strip()


def parse_dt(iso):
    if not iso:
        return None
    try:
        return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def fmt_dt(iso, fmt="%m月%d日 %H:%M"):
    dt = parse_dt(iso)
    if dt is None:
        return iso or "不明"
    return dt.astimezone(JST).strftime(fmt)
