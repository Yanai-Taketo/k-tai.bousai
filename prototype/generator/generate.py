#!/usr/bin/env python3
"""軽量防災サイト プロトタイプ生成器。

気象庁 防災情報XML の Atom フィード(PULL型)から警報・注意報と地震情報を取得し、
数KB級の静的HTMLを prototype/site/ に生成する。標準ライブラリのみ使用。

データ源(いずれも無償・ベストエフォート):
  - https://www.data.jma.go.jp/developer/xml/feed/extra.xml   (高頻度: 警報・注意報等)
  - https://www.data.jma.go.jp/developer/xml/feed/extra_l.xml (長期: 同上、過去分)
  - https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml   (高頻度: 地震・津波・火山)

出典: 気象庁ホームページ(利用規約 https://www.jma.go.jp/jma/kishou/info/coment.html)
"""

import concurrent.futures
import datetime
import gzip
import html
import os
import re
import ssl
import sys
import urllib.request
import xml.etree.ElementTree as ET

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.normpath(os.path.join(BASE, "..", "site"))
CACHE = os.path.join(BASE, ".cache")

ATOM = "{http://www.w3.org/2005/Atom}"

FEED_EXTRA = "https://www.data.jma.go.jp/developer/xml/feed/extra.xml"
FEED_EXTRA_L = "https://www.data.jma.go.jp/developer/xml/feed/extra_l.xml"
FEED_EQVOL = "https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml"

JST = datetime.timezone(datetime.timedelta(hours=9))


def _ssl_context():
    cafile = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"
    if os.path.exists(cafile):
        return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


CTX = _ssl_context()


def fetch(url, cache_ok=False):
    """URLを取得してbytesを返す。電文XMLは内容不変なのでキャッシュ可。"""
    name = os.path.join(CACHE, url.rsplit("/", 1)[-1])
    if cache_ok and os.path.exists(name):
        with open(name, "rb") as f:
            return f.read()
    req = urllib.request.Request(url, headers={"User-Agent": "k-tai.bousai prototype (research)"})
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        data = r.read()
    if cache_ok:
        os.makedirs(CACHE, exist_ok=True)
        with open(name, "wb") as f:
            f.write(data)
    return data


def strip_ns(tag):
    return tag.rsplit("}", 1)[-1]


def findall_anyns(elem, name):
    return [e for e in elem.iter() if strip_ns(e.tag) == name]


def text_of(elem, name, default=""):
    for e in elem.iter():
        if strip_ns(e.tag) == name:
            return (e.text or default).strip()
    return default


def parse_feed(data):
    """Atomフィードを entry の辞書リストに変換する。"""
    root = ET.fromstring(data)
    entries = []
    for en in root.findall(f"{ATOM}entry"):
        link = en.find(f"{ATOM}link")
        entries.append(
            {
                "title": (en.findtext(f"{ATOM}title") or "").strip(),
                "updated": (en.findtext(f"{ATOM}updated") or "").strip(),
                "author": (en.findtext(f"{ATOM}author/{ATOM}name") or "").strip(),
                "content": (en.findtext(f"{ATOM}content") or "").strip(),
                "href": link.get("href") if link is not None else "",
            }
        )
    feed_updated = (root.findtext(f"{ATOM}updated") or "").strip()
    return feed_updated, entries


def office_code(href):
    m = re.search(r"_([0-9]{6})\.xml$", href)
    return m.group(1) if m else None


def latest_vpww54_per_office(entry_lists):
    """警報・注意報電文(VPWW54)を官署コードごとに最新1件へ絞る。"""
    latest = {}
    for entries in entry_lists:
        for en in entries:
            if "_VPWW54_" not in en["href"]:
                continue
            code = office_code(en["href"])
            if not code:
                continue
            if code not in latest or en["updated"] > latest[code]["updated"]:
                latest[code] = en
    return latest


def parse_vpww54(data):
    """警報・注意報電文から、見出しと地域ごとの発表状況を取り出す。"""
    root = ET.fromstring(data)
    head = next((el for el in root.iter() if strip_ns(el.tag) == "Head"), root)
    out = {
        "title": text_of(head, "Title"),  # 例: 宮城県気象警報・注意報
        "report_dt": text_of(head, "ReportDateTime"),
        "headline": "",
        "areas": [],  # (地域名, [(種別, 状態), ...])
    }
    for h in findall_anyns(head, "Headline"):
        out["headline"] = text_of(h, "Text")
        break
    warning = None
    prefer = ("気象警報・注意報（市町村等をまとめた地域等）", "気象警報・注意報（一次細分区域等）")
    ws = {w.get("type"): w for w in findall_anyns(root, "Warning")}
    for p in prefer:
        if p in ws:
            warning = ws[p]
            break
    if warning is None:
        return out
    for item in list(warning):
        if strip_ns(item.tag) != "Item":
            continue
        area = ""
        kinds = []
        for child in list(item):
            t = strip_ns(child.tag)
            if t == "Area":
                area = text_of(child, "Name")
            elif t == "Kind":
                # Kind直下のみ参照(子要素のPropertyなどを拾わない)
                d = {}
                for c in list(child):
                    cn = strip_ns(c.tag)
                    if cn in ("Name", "Status", "Condition") and cn not in d:
                        d[cn] = (c.text or "").strip()
                name = d.get("Name", "")
                if d.get("Condition"):
                    name = f"{name}({d['Condition']})"
                if name:
                    kinds.append((name, d.get("Status", "")))
        out["areas"].append((area, kinds))
    return out


def severity_of(parsed):
    """電文全体の最上位区分を返す(表示順位付け用)。"""
    names = [k for _, kinds in parsed["areas"] for k, _s in kinds]
    joined = " ".join(names) + " " + parsed.get("headline", "")
    if "特別警報" in joined:
        return 3, "特別警報"
    if "危険警報" in joined:
        return 3, "危険警報"
    if "警報" in joined:
        return 2, "警報"
    if "注意報" in joined:
        return 1, "注意報"
    return 0, "発表なし"


def parse_vxse53(data):
    """震源・震度電文から要点を取り出す。"""
    root = ET.fromstring(data)
    mag = ""
    for e in root.iter():
        if strip_ns(e.tag) == "Magnitude":
            mag = (e.text or "").strip()
            break
    return {
        "origin": text_of(root, "OriginTime"),
        "hypo": text_of(root, "Name"),  # Hypocenter/Area/Name が最初のName
        "mag": mag,
        "maxint": text_of(root, "MaxInt"),
        "report_dt": text_of(root, "ReportDateTime"),
    }


def fmt_dt(iso):
    if not iso:
        return "不明"
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(JST)
        return dt.strftime("%m月%d日 %H:%M")
    except ValueError:
        return iso


e = html.escape

CSS = (
    "body{font-family:sans-serif;line-height:1.6;margin:0 auto;padding:8px;max-width:40em;"
    "background:#fff;color:#111}h1{font-size:1.2em;margin:.4em 0}h2{font-size:1.05em;"
    "border-bottom:1px solid #999;margin:1em 0 .3em}ul{margin:.3em 0;padding-left:1.4em}"
    "a{color:#0645ad}small,.n{color:#444}.w3{font-weight:bold}.hd{background:#eee;padding:4px 8px}"
    "@media(prefers-color-scheme:dark){body{background:#111;color:#eee}a{color:#8cb4ff}"
    "small,.n{color:#aaa}.hd{background:#222}}"
)


def page(title, body, generated, data_note=""):
    """共通レイアウト。素のHTML+インラインCSSのみ、JSなし。"""
    return (
        "<!DOCTYPE html><html lang=ja><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{e(title)}</title><style>{CSS}</style></head><body>"
        f"<div class=hd>ページ生成: {e(generated)} JST{e(data_note)}</div>"
        f"{body}"
        "<h2>このサイトについて</h2>"
        "<p class=n>本ページは軽量防災サイトの<strong>プロトタイプ(実験版)</strong>です。"
        "出典: <a href=\"https://www.jma.go.jp/\">気象庁ホームページ</a>の防災情報XMLを加工して作成。"
        "発表主体はすべて気象庁です。情報の正確性・即時性は保証されません。"
        "<strong>避難の判断は必ずお住まいの自治体の発表に従ってください。</strong></p>"
        "<p class=n><a href=\"index.html\">トップ</a> | <a href=\"about.html\">詳細説明</a></p>"
        "</body></html>"
    )


def minify(s):
    return re.sub(r">\s+<", "><", s)


def write_page(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = minify(content).encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    gz = len(gzip.compress(data, 9))
    rel = os.path.relpath(path, SITE)
    print(f"  {rel}: {len(data):,} bytes (gzip {gz:,})")


def main():
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    print("フィード取得中...")
    _, extra = parse_feed(fetch(FEED_EXTRA))
    try:
        _, extra_l = parse_feed(fetch(FEED_EXTRA_L))
    except Exception as ex:  # 長期フィードは補助扱い
        print(f"  長期フィード取得失敗(続行): {ex}", file=sys.stderr)
        extra_l = []
    feed_updated, eqvol = parse_feed(fetch(FEED_EQVOL))

    # --- 警報・注意報: 官署ごとに最新電文を取得 ---
    latest = latest_vpww54_per_office([extra, extra_l])
    print(f"警報・注意報電文: {len(latest)} 官署分を取得...")
    parsed = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch, en["href"], True): code for code, en in latest.items()}
        for fut in concurrent.futures.as_completed(futs):
            code = futs[fut]
            try:
                parsed[code] = parse_vpww54(fut.result())
            except Exception as err:
                print(f"  電文取得/解析失敗 {code}: {err}", file=sys.stderr)

    # --- 地震: 最新の震源・震度電文 ---
    eq_entries = [en for en in eqvol if "_VXSE53_" in en["href"]]
    seen, eq_latest = set(), []
    for en in eq_entries:
        if en["href"] in seen:
            continue
        seen.add(en["href"])
        eq_latest.append(en)
    eq_latest = eq_latest[:10]
    quakes = []
    for en in eq_latest:
        try:
            quakes.append(parse_vxse53(fetch(en["href"], True)))
        except Exception as err:
            print(f"  地震電文失敗: {err}", file=sys.stderr)

    # --- 津波関連電文が直近にあるか(プロトタイプ簡易判定) ---
    tsunami = [en for en in eqvol if re.search(r"_VTSE(41|51|52)_", en["href"])]

    # --- 都道府県ページ ---
    print("ページ生成:")
    rows = []
    for code, p in sorted(parsed.items()):
        pref = p["title"].replace("気象警報・注意報", "").strip() or code
        sev, label = severity_of(p)
        body = [f"<h1>{e(p['title'])}</h1>"]
        body.append(f"<p class=n>気象庁発表: {e(fmt_dt(p['report_dt']))}</p>")
        if p["headline"]:
            body.append(f"<p>{e(p['headline'])}</p>")
        for area, kinds in p["areas"]:
            active = [(k, s) for k, s in kinds if s != "解除" and k != "解除"]
            if not active:
                continue
            items = "、".join(
                f"<span class=w3>{e(k)}</span>" if ("警報" in k and "注意報" not in k) else e(k)
                for k, _s in active
            )
            body.append(f"<h2>{e(area)}</h2><p>{items}</p>")
        if len(body) <= 3:
            body.append("<p>現在、発表中の警報・注意報はありません。</p>")
        write_page(
            os.path.join(SITE, "warn", f"{code}.html"),
            page(p["title"], "".join(body), now, f" / 気象庁発表 {fmt_dt(p['report_dt'])}"),
        )
        rows.append((sev, label, pref, code, p["report_dt"]))

    # --- 地震ページ ---
    qbody = ["<h1>地震情報(震源・震度)</h1>"]
    if not quakes:
        qbody.append("<p>直近の震源・震度情報はありません。</p>")
    for q in quakes:
        qbody.append(
            f"<p><span class=w3>{e(fmt_dt(q['origin']))}ごろ</span> {e(q['hypo'])} "
            f"M{e(q['mag'] or '不明')} 最大震度{e(q['maxint'] or '不明')}</p>"
        )
    write_page(os.path.join(SITE, "eq.html"), page("地震情報", "".join(qbody), now))

    # --- トップページ ---
    ibody = ["<h1>防災情報(文字版・実験)</h1>"]
    if tsunami:
        t = tsunami[0]
        ibody.append(
            f"<p class=w3>【津波関連情報あり】{e(t['title'])} ({e(fmt_dt(t['updated']))}) "
            f"{e(t['content'][:100])}… 詳細は<a href=\"https://www.jma.go.jp/bosai/\">気象庁</a>へ</p>"
        )
    if quakes:
        q = quakes[0]
        ibody.append(
            f"<p>最新の地震: {e(fmt_dt(q['origin']))}ごろ {e(q['hypo'])} "
            f"M{e(q['mag'] or '?')} 最大震度{e(q['maxint'] or '?')} → <a href=\"eq.html\">地震情報一覧</a></p>"
        )
    ibody.append("<h2>都道府県の気象警報・注意報</h2>")
    for sev_label in ((3, "特別警報・危険警報"), (2, "警報"), (1, "注意報のみ"), (0, "発表なし")):
        group = [r for r in rows if r[0] == sev_label[0]]
        if not group:
            continue
        links = " ".join(
            f'<a href="warn/{code}.html">{e(pref)}</a>' for _s, _l, pref, code, _dt in group
        )
        cls = " class=w3" if sev_label[0] >= 3 else ""
        ibody.append(f"<p><span{cls}>{sev_label[1]}</span>: {links}</p>")
    write_page(os.path.join(SITE, "index.html"), page("防災情報 文字版(実験)", "".join(ibody), now))

    # --- 説明ページ ---
    about = (
        "<h1>このサイトについて(プロトタイプ)</h1>"
        "<p>通信環境が悪い場所・混雑した環境でも読めることを目指した、文字中心の軽量防災サイトの実験版です。"
        "1ページ数KB(スマホ向け防災地図サイトの数百分の一以下)を目標にしています。</p>"
        "<h2>データについて</h2>"
        "<p>気象庁「防災情報XMLフォーマット形式電文(PULL型)」の高頻度フィードを定期取得して生成しています。"
        "フィードは無償・ベストエフォート提供であり、配信の遅延・停止があり得ます。"
        "各ページ上部の「ページ生成」時刻が古い場合、情報が最新でない可能性があります。</p>"
        "<h2>このサイトが向かない状況</h2>"
        "<p>基地局停波・圏外では本サイトも閲覧できません。緊急速報メール・ラジオ等を利用してください。"
        "避難指示・避難所開設は自治体の発表を確認してください。</p>"
    )
    write_page(os.path.join(SITE, "about.html"), page("このサイトについて", about, now))

    print(f"完了: {len(rows)} 都道府県 / 地震 {len(quakes)} 件 / フィード更新 {feed_updated}")


if __name__ == "__main__":
    main()
