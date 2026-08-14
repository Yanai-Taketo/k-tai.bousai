"""静的HTMLの生成(素のHTML+最小インラインCSS・JSなし)。

要件: N-1〜N-3(軽量性)、R-1〜R-5(取得時刻・発表主体・出典・劣化警告・非公式明示)。
警戒レベル配色は気象庁配色(L5黒/L4紫/L3赤/L2黄)に合わせるが、色のみに依存せず
名称テキストを常に併記する。
"""

import gzip
import html
import os
import re

from .jmautil import fmt_dt

e = html.escape

CSS = (
    "body{font-family:sans-serif;line-height:1.55;margin:0 auto;padding:8px;max-width:40em;"
    "background:#fff;color:#111}h1{font-size:1.15em;margin:.4em 0}"
    "h2{font-size:1em;border-bottom:1px solid #999;margin:1em 0 .3em}"
    "ul{margin:.3em 0;padding-left:1.4em}a{color:#0645ad}small,.n{color:#444}"
    ".hd{background:#eee;padding:4px 8px;font-size:.85em}"
    ".b{display:inline-block;padding:0 .35em;border-radius:3px;font-weight:bold}"
    ".s5{background:#111;color:#fff;border:1px solid #666}.s4{background:#a0a;color:#fff}"
    ".s3{background:#d02000;color:#fff}.s2{background:#f5e08a;color:#111}"
    ".warn{border-left:4px solid #d00;padding:4px 8px;background:#fee;margin:.5em 0}"
    "@media(prefers-color-scheme:dark){body{background:#111;color:#eee}a{color:#8cb4ff}"
    "small,.n{color:#aaa}.hd{background:#222}.warn{background:#411;border-color:#f66}}"
)


def badge(severity, name):
    cls = {5: "s5", 4: "s4", 3: "s3", 2: "s2"}.get(severity)
    if cls:
        return f'<span class="b {cls}">{e(name)}</span>'
    return e(name)


def page(title, body, generated, root="", banner=""):
    """共通レイアウト。rootは相対パスの接頭辞(下層ページは "../")。"""
    warn = f'<div class=warn>{banner}</div>' if banner else ""
    return (
        "<!DOCTYPE html><html lang=ja><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{e(title)}</title><style>{CSS}</style></head><body>"
        f"<div class=hd>データ取得: {e(generated)} JST | 非公式の軽量ミラーです</div>"
        f"{warn}{body}"
        "<h2>ご注意</h2>"
        "<p class=n>本サイトは個人運営の<strong>非公式</strong>サイトです。"
        "掲載情報はすべて気象庁の発表の転載であり、発表主体・発表時刻は各項目に記載のとおりです。"
        "情報の正確性・即時性は保証されません。"
        "<strong>避難や身を守る行動の判断は、必ずお住まいの自治体・気象庁の発表に従ってください。</strong>"
        "圏外・基地局停波時は本サイトも閲覧できません(緊急速報メール・ラジオ等をご利用ください)。</p>"
        f"<p class=n>出典: <a href=\"https://www.jma.go.jp/\">気象庁ホームページ</a> | "
        f'<a href="{root}index.html">全国トップ</a> | '
        f'<a href="{root}eq.html">地震</a> | '
        f'<a href="{root}tsunami.html">津波</a> | '
        f'<a href="{root}about.html">このサイトについて</a></p>'
        "</body></html>"
    )


def minify(s):
    return re.sub(r">\s+<", "><", s)


def write_page(site_dir, rel, content):
    """ページを書き出し、(相対パス, 生バイト, gzipバイト) を返す。"""
    path = os.path.join(site_dir, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = minify(content).encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    return rel, len(data), len(gzip.compress(data, 9))


def render_pref(name, warn, sokuho, fd, fw, generated, banner):
    """府県ページ: 警報・注意報+気象防災速報+天気予報(1リクエストで完結)。"""
    body = [f"<h1>{e(name)}の防災情報</h1>"]

    body.append("<h2>気象警報・注意報</h2>")
    if warn is None:
        body.append("<p class=n>警報・注意報の電文を取得できませんでした。"
                    '<a href="https://www.jma.go.jp/bosai/warning/">気象庁</a>で確認してください。</p>')
    else:
        body.append(f"<p class=n>気象庁発表: {e(fmt_dt(warn['report_dt']))}</p>")
        for h in warn["headlines"][:2]:
            if h:
                body.append(f"<p>{e(h)}</p>")
        shown = False
        for area, kinds in warn["areas"]:
            if not kinds:
                continue
            shown = True
            from .parse_warnings import severity_of

            items = "、".join(badge(severity_of(k["name"]), k["name"]) for k in kinds)
            body.append(f"<p><strong>{e(area)}</strong>: {items}</p>")
        if not shown:
            body.append("<p>現在、発表中の警報・注意報はありません。</p>")

    if sokuho:
        body.append("<h2>気象防災速報(直近24時間)</h2>")
        for s in sokuho:
            body.append(
                f"<p><strong>{e(s['title'])}</strong>"
                f"<br><small>{e(fmt_dt(s['report_dt']))} 気象庁発表</small><br>{e(s['text'])}</p>"
            )

    body.append("<h2>天気予報</h2>")
    if fd is None:
        body.append("<p class=n>天気予報の電文を取得できませんでした。</p>")
    else:
        body.append(f"<p class=n>気象庁発表: {e(fmt_dt(fd['report_dt']))}</p>")
        for a in fd["areas"]:
            w = " / ".join(f"{e(t)}: {e(x)}" for t, x in a["weathers"])
            body.append(f"<p><strong>{e(a['name'])}</strong><br>{w}")
            if a["pops"]:
                pops = "、".join(f"{e(t)} {e(v)}%" for t, v in a["pops"] if v)
                body.append(f"<br><small>降水確率: {pops}</small>")
            body.append("</p>")
        if fd["stations"]:
            temps = " / ".join(
                f"{e(s['name'])} " + " ".join(f"{e(t)}{e(v)}℃" for t, v in s["temps"])
                for s in fd["stations"][:4]
            )
            body.append(f"<p><small>気温: {temps}</small></p>")

    if fw is not None and fw["areas"]:
        body.append("<h2>週間天気予報</h2>")
        body.append(f"<p class=n>気象庁発表: {e(fmt_dt(fw['report_dt']))}</p>")
        for a in fw["areas"][:3]:
            days = "、".join(
                f"{e(fmt_dt(d, '%d日'))}{e(wx)}" + (f"({e(p)}%)" if p else "")
                for d, wx, p in a["days"]
                if wx
            )
            body.append(f"<p><strong>{e(a['name'])}</strong><br><small>{days}</small></p>")
        for s in fw["stations"][:2]:
            days = "、".join(
                f"{e(fmt_dt(d, '%d日'))}{e(lo)}/{e(hi)}℃" for d, lo, hi in s["days"] if lo or hi
            )
            if days:
                body.append(f"<p><small>{e(s['name'])}の気温(最低/最高): {days}</small></p>")

    return page(f"{name}の防災情報", "".join(body), generated, root="../", banner=banner)


def render_index(pref_rows, quakes, tsunami, sokuho_all, generated, banner):
    """全国トップ。pref_rows: [(severity, name, code)]"""
    body = ["<h1>防災情報(文字版)</h1>"]

    if tsunami and tsunami["active"]:
        areas = "、".join(
            f"{e(i['kind'])}: {e('、'.join(i['areas'][:8]))}" for i in tsunami["items"][:4]
        )
        body.append(
            f'<p class=warn><strong>【津波情報 発表中】</strong>{areas} → <a href="tsunami.html">詳細</a></p>'
        )

    if sokuho_all:
        body.append("<h2>気象防災速報(直近24時間)</h2><ul>")
        for code, s in sokuho_all[:8]:
            body.append(
                f'<li><a href="p/{e(code)}.html">{e(s["title"])}</a> <small>{e(fmt_dt(s["report_dt"]))}</small></li>'
            )
        body.append("</ul>")

    body.append("<h2>都道府県の気象警報・注意報と天気予報</h2>")
    groups = (
        (5, "特別警報 発表中"),
        (4, "危険警報 発表中"),
        (3, "警報 発表中"),
        (2, "注意報のみ"),
        (0, "発表なし"),
    )
    for sev, label in groups:
        group = [r for r in pref_rows if r[0] == sev]
        if not group:
            continue
        links = " ".join(f'<a href="p/{e(c)}.html">{e(n)}</a>' for _s, n, c in group)
        head = badge(sev, label) if sev >= 2 else e(label)
        body.append(f"<p>{head}<br>{links}</p>")

    if quakes:
        q = quakes[0]
        body.append("<h2>最新の地震</h2>")
        for q in quakes[:3]:
            body.append(
                f"<p>{e(fmt_dt(q['origin']))}ごろ {e(q['hypo'])} "
                + (f"M{e(q['mag'])} " if q["mag"] else "")
                + f"最大震度{e(q['maxint'] or '調査中')}</p>"
            )
        body.append('<p><a href="eq.html">地震情報一覧へ</a></p>')

    return page("防災情報 文字版", "".join(body), generated, banner=banner)


def render_eq(quakes, generated, banner):
    body = ["<h1>地震情報</h1>"]
    if not quakes:
        body.append("<p>直近の地震情報はありません。</p>")
    for q in quakes:
        body.append(
            f"<p><strong>{e(fmt_dt(q['origin']))}ごろ</strong> {e(q['hypo'])} "
            + (f"M{e(q['mag'])} " if q["mag"] else "")
            + f"最大震度{e(q['maxint'] or '調査中')}"
            f"<br><small>{e(q['kind'])} / 気象庁発表 {e(fmt_dt(q['report_dt']))}</small></p>"
        )
    return page("地震情報", "".join(body), generated, banner=banner)


def render_tsunami(ts, generated, banner):
    body = ["<h1>津波情報</h1>"]
    if ts is None or not ts["active"]:
        body.append("<p>現在、津波警報・注意報等は発表されていません。</p>")
        if ts is not None and ts["report_dt"]:
            body.append(f"<p class=n>最終電文: {e(fmt_dt(ts['report_dt']))} 気象庁発表</p>")
    else:
        body.append(f"<p class=n>気象庁発表: {e(fmt_dt(ts['report_dt']))}</p>")
        if ts["headline"]:
            body.append(f"<p class=warn>{e(ts['headline'])}</p>")
        for i in ts["items"]:
            sev = 5 if "大津波" in i["kind"] else 4 if "警報" in i["kind"] else 2
            body.append(
                f"<p>{badge(sev, i['kind'])}<br>{e('、'.join(i['areas']))}</p>"
            )
        body.append(
            '<p>到達予想時刻・予想される高さは<a href="https://www.jma.go.jp/bosai/">気象庁</a>で確認してください。</p>'
        )
    return page("津波情報", "".join(body), generated, banner=banner)


def render_about(generated):
    body = (
        "<h1>このサイトについて</h1>"
        "<p>通信環境が悪い場所・回線が混雑・速度制限された状態でも読めることを目指した、"
        "文字中心の軽量防災情報サイトです。1ページ数KB(一般的な防災地図サイトの数百分の一以下)で、"
        "画像・JavaScriptを使わずに表示できます。</p>"
        "<h2>掲載している情報</h2>"
        "<p>気象庁「防災情報XMLフォーマット形式電文(PULL型)」の無償フィードを定期取得し、"
        "気象警報・注意報(2026年5月運用開始の新体系)、気象防災速報、地震・津波情報、"
        "府県天気予報・週間天気予報を<strong>改変せずそのまま</strong>掲載しています。"
        "発表主体はすべて気象庁です。</p>"
        "<h2>掲載していない情報</h2>"
        "<p>避難指示・避難所の開設状況は掲載していません(個人が機械可読で入手できる公式経路が"
        "存在しないため)。<strong>避難に関する情報は、お住まいの自治体の発表・緊急速報メール・"
        "テレビ・ラジオで確認してください。</strong></p>"
        "<h2>情報の鮮度と限界</h2>"
        "<p>フィードは無償・ベストエフォート提供のため、配信の遅延・停止があり得ます。"
        "各ページ上部の「データ取得」時刻が古い場合、情報が最新でない可能性があります。"
        "その場合は気象庁ホームページ等で確認してください。"
        "また、圏外・基地局停波の環境では本サイトも閲覧できません。"
        "本サイトは公式情報の補完であり、代替ではありません。</p>"
        "<h2>出典・ライセンス</h2>"
        "<p>データの出典: 気象庁ホームページ(防災情報XML)。"
        "本サイトの生成システムはオープンソース(MITライセンス)で公開しています: "
        '<a href="https://github.com/Yanai-Taketo/k-tai.bousai">GitHub</a></p>'
    )
    return page("このサイトについて", body, generated)
