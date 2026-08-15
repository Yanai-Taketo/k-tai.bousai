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

# 配色は気象庁「気象庁ホームページにおける配色に関する設定指針」の公式RGBに準拠。
# 赤#ff2800の文字色は黒(白字は3.78:1でWCAG AA不合格、黒字5.6:1で合格——
# research/2026-08-14-layout-research.md のコントラスト実測)。
CSS = (
    "body{font-family:sans-serif;line-height:1.55;margin:0 auto;padding:8px;max-width:40em;"
    "background:#fff;color:#111}h1{font-size:1.15em;margin:.4em 0}"
    "h2{font-size:1em;border-bottom:1px solid #999;margin:1em 0 .3em}"
    "ul{margin:.3em 0;padding-left:1.4em}a{color:#0645ad}small,.n{color:#444}"
    ".hd{background:#eee;padding:4px 8px;font-size:.85em}"
    ".b{display:inline-block;padding:0 .3em;border-radius:2px;margin:0 .2em .1em 0;font-weight:bold}"
    ".s5{background:#0c000c;color:#fff;border:1px solid #888}.s4{background:#a0a;color:#fff}"
    ".s3{background:#ff2800;color:#111}.s2{background:#f2e700;color:#111;border:1px solid #999}"
    ".band{padding:4px 8px;margin:.6em 0;font-weight:bold}"
    "table{border-collapse:collapse;margin:.3em 0;width:100%}"
    "th,td{border:1px solid #aaa;padding:2px 6px;text-align:left;vertical-align:top;font-size:.95em}"
    ".tw{overflow-x:auto}.tw:focus{outline:2px solid #06c}"
    ".r{margin:.25em 0}.r b{display:inline-block;min-width:5.5em;color:#444}"
    ".warn{border-left:4px solid #d00;padding:4px 8px;background:#fee;margin:.5em 0}"
    ".safe{border-left:4px solid #06c;padding:2px 8px;background:#eef4ff}"
    "@media(prefers-color-scheme:dark){body{background:#111;color:#eee}a{color:#8cb4ff}"
    "small,.n{color:#aaa}.hd{background:#222}th,td{border-color:#555}"
    ".warn{background:#411;border-color:#f66}.r b{color:#aaa}.tw:focus{outline-color:#8cb4ff}"
    ".safe{background:#132039;border-color:#5a8ad6}}"
)


def badge(severity, name):
    cls = {5: "s5", 4: "s4", 3: "s3", 2: "s2"}.get(severity)
    if cls:
        return f'<span class="b {cls}">{e(name)}</span>'
    return e(name)


def page(title, body, generated, root="./", banner=""):
    """共通レイアウト。

    内部リンクは拡張子なし(/p/130000 等)にする。出力はフラットな
    `p/130000.html` のままだが、Cloudflare Pages・GitHub Pages とも
    拡張子なしURLをそのまま配信する(実測: 全ページ種別で0リダイレクト)。
    `.html`付きだとCloudflareが拡張子なしへ308、末尾スラッシュ付きだと
    Cloudflareがスラッシュを除去する308を返し、いずれも1往復増える
    (低速回線では0.2〜0.5秒の損)。
    rootは階層に応じた接頭辞("./" = 直下, "../" = p/ や eq/ の下)。
    """
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
        f'<a href="{root}">全国トップ</a> | '
        f'<a href="{root}eq">地震</a> | '
        f'<a href="{root}tsunami">津波</a> | '
        f'<a href="{root}about">このサイトについて</a></p>'
        "</body></html>"
    )


def minify(s):
    # 改行を含む空白のみ除去する。リンク間の意図的な半角スペース(県名の区切り)は保持。
    return re.sub(r">[ \t]*\n\s*<", "><", s)


def write_page(site_dir, rel, content):
    """ページを書き出し、(相対パス, 生バイト, gzipバイト) を返す。"""
    path = os.path.join(site_dir, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = minify(content).encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    return rel, len(data), len(gzip.compress(data, 9))


LEVEL_GUIDE = (
    "<h2>警戒レベルと取るべき行動</h2><ul>"
    '<li><span class="b s5">特別警報</span>レベル5相当: 命の危険。直ちに安全確保</li>'
    '<li><span class="b s4">危険警報</span>レベル4相当: 危険な場所から全員避難</li>'
    '<li><span class="b s3">警報</span>レベル3相当: 高齢者等は危険な場所から避難</li>'
    '<li><span class="b s2">注意報</span>レベル2: 自らの避難行動を確認</li></ul>'
)


def render_pref(name, warn, sokuho, fd, fw, generated, banner):
    """府県ページ(モック案C準拠): 帯+概況→警報表→速報→天気予報→警戒レベル。

    警報・注意報は1テーブルに統合(行=発表区域、列2本固定、「発表なし」明記)。
    一次細分区域の区切り行は区域階層表(area.json由来)の整備後に追加する。
    """
    from .parse_warnings import severity_of

    body = [f"<h1>{e(name)}の防災情報</h1>"]

    # 最大レベルの帯(警報以上のときのみ)と概況文は警報セクションの前に置く
    if warn is not None:
        max_sev = warn["max_severity"]
        if max_sev >= 3:
            top_names, top_areas = [], []
            for area, kinds in warn["areas"]:
                for k in kinds:
                    if severity_of(k["name"]) == max_sev:
                        if k["name"] not in top_names:
                            top_names.append(k["name"])
                        top_areas.append(area)
                        break
            areas_txt = "、".join(top_areas[:3]) + ("ほか" if len(top_areas) > 3 else "")
            body.append(
                f'<p class="band s{max_sev}">{e("、".join(top_names[:2]))} 発表中'
                f"({e(areas_txt)})</p>"
            )
        for h in warn["headlines"][:2]:
            if h:
                body.append(f"<p>{e(h)}</p>")

    body.append("<h2 id=wh>気象警報・注意報</h2>")
    if warn is None:
        body.append("<p class=n>警報・注意報の電文を取得できませんでした。"
                    '<a href="https://www.jma.go.jp/bosai/warning/">気象庁</a>で確認してください。</p>')
    else:
        body.append(f"<p class=n>気象庁発表: {e(fmt_dt(warn['report_dt']))}</p>")
        if warn["max_severity"] >= 2:
            rows = ["<tr><th scope=col>発表区域</th><th scope=col>発表中の警報・注意報</th></tr>"]
            for area, kinds in warn["areas"]:
                if kinds:
                    chips = " ".join(
                        badge(severity_of(k["name"]), k["name"]) for k in kinds
                    )
                    rows.append(f"<tr><th scope=row>{e(area)}</th><td>{chips}</td></tr>")
                else:
                    rows.append(
                        f"<tr><th scope=row>{e(area)}</th><td class=n>発表なし</td></tr>"
                    )
            body.append(
                "<div class=tw role=region aria-labelledby=wh tabindex=0><table>"
                + "".join(rows)
                + "</table></div>"
            )
        else:
            body.append("<p>警報・注意報は発表されていません。</p>")

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

    body.append(LEVEL_GUIDE)
    return page(f"{name}の防災情報", "".join(body), generated, root="../", banner=banner)


def render_index(pref_rows, quakes, tsunami, sokuho_all, generated, banner):
    """全国トップ(モック案D準拠・決定#17/#21)。pref_rows: [(severity, name, code)]

    重要情報欄は発表中のものだけを表示し、平時は1行に縮退する。
    県リンクは地方順固定で、警報以上のときだけ県名自体を色チップ化する。
    """
    from .offices import REGIONS, SHORT_NAMES

    body = ["<h1>防災情報(文字版)</h1>"]

    body.append("<h2>いま発表中の重要情報</h2>")
    important = False
    if tsunami and tsunami["active"]:
        important = True
        areas = "、".join(
            f"{e(i['kind'])}: {e('、'.join(i['areas'][:8]))}" for i in tsunami["items"][:4]
        )
        body.append(
            f'<p class=warn><strong>【津波情報 発表中】</strong>{areas} → <a href="tsunami">詳細</a></p>'
        )
    for sev, label in ((5, "特別警報"), (4, "危険警報"), (3, "警報")):
        group = [(n, c) for s, n, c in pref_rows if s == sev]
        if not group:
            continue
        important = True
        links = " ".join(f'<a href="p/{e(c)}">{e(n)}</a>' for n, c in group)
        body.append(f"<p>{badge(sev, label)}{links}</p>")
    for code, s in sokuho_all[:5]:
        important = True
        body.append(
            f'<p><a href="p/{e(code)}">{e(s["title"])}</a> '
            f"<small class=n>{e(fmt_dt(s['report_dt']))} 気象庁発表</small></p>"
        )
    if not important:
        body.append("<p>現在、特別警報・危険警報・警報および津波警報等はありません。</p>")

    body.append("<h2>都道府県を選ぶ(地方順)</h2>")
    sev_by_code = {c: s for s, _n, c in pref_rows}
    for region, codes in REGIONS:
        links = []
        for c in codes:
            sev = sev_by_code.get(c, 0)
            short = e(SHORT_NAMES.get(c, c))
            if sev >= 3:
                links.append(f'<a href="p/{c}"><span class="b s{sev}">{short}</span></a>')
            else:
                links.append(f'<a href="p/{c}">{short}</a>')
        body.append(f"<p class=r><b>{e(region)}</b> {' '.join(links)}</p>")
    body.append(
        '<p class=n>色付きの県は発表中: <span class="b s5">特別警報</span> '
        '<span class="b s4">危険警報</span> <span class="b s3">警報</span> / '
        "注意報は各府県ページで</p>"
    )

    if quakes:
        from .parse_eqtsunami import int_label

        q = quakes[0]
        body.append(
            "<h2>最新の地震</h2>"
            f"<p>{e(fmt_dt(q['origin']))}ころ {e(q['hypo'])} "
            + (f"M{e(q['mag'])} " if q["mag"] else "")
            + (f"最大震度{e(int_label(q['maxint']))}" if q["maxint"] else "最大震度調査中")
            + ' → <a href="eq">一覧</a></p>'
        )

    return page("防災情報 文字版", "".join(body), generated, banner=banner)


EQ_GZIP_BUDGET = 6 * 1024  # 設計書§4の /eq 予算

_ID_SAFE = re.compile(r"[^0-9A-Za-z_-]")


def eq_event_slug(q):
    """EventIDをURL/ファイル名として安全な文字列にする。無ければNone。"""
    eid = _ID_SAFE.sub("", q.get("event_id") or "")
    return eid or None


def eq_detail_rel(q):
    """地震詳細ページの出力パス。EventIDが無い電文はNone(詳細ページを作らない)。"""
    slug = eq_event_slug(q)
    return f"eq/{slug}.html" if slug else None


def eq_detail_href(q):
    """地震一覧ページ(/eq)から詳細ページへのリンク。/eq のベースは / なので eq/ を付ける。"""
    slug = eq_event_slug(q)
    return f"eq/{slug}" if slug else None


def _group_intensity(rows, gran):
    """観測結果を震度降順・県ごとにまとめる。

    gran: "city"=市町村名まで / "area"=細分区域まで / "pref"=県名のみ。
    粒度を落とすときは、まとめた単位の最大震度を採る。
    """
    from .parse_eqtsunami import int_rank

    merged = {}
    order = []
    for r in rows:
        if gran == "pref":
            key, name = (r["pref"],), ""
        elif gran == "area":
            key, name = (r["pref"], r["area"] or r["pref"]), r["area"] or r["pref"]
        else:
            key, name = (
                (r["pref"], r["area"], r["city"] or r["area"] or r["pref"]),
                r["city"] or r["area"] or r["pref"],
            )
        if key not in merged:
            merged[key] = {"int": r["int"], "pref": r["pref"], "name": name}
            order.append(key)
        elif int_rank(r["int"]) > int_rank(merged[key]["int"]):
            merged[key]["int"] = r["int"]

    blocks = []
    for value in sorted({m["int"] for m in merged.values()}, key=int_rank, reverse=True):
        prefs, pref_order = {}, []
        for key in order:
            m = merged[key]
            if m["int"] != value:
                continue
            if m["pref"] not in prefs:
                prefs[m["pref"]] = []
                pref_order.append(m["pref"])
            if m["name"]:
                prefs[m["pref"]].append(m["name"])
        blocks.append((value, [(p, prefs[p]) for p in pref_order]))
    return blocks


def _eq_detail_body(q, gran):
    """地震詳細ページの本文(粒度指定)。"""
    from .parse_eqtsunami import int_label

    body = [f"<h1>{e(fmt_dt(q['origin']))}ころの地震</h1>"]
    body.append(f"<p class=n>{e(q['kind'])} / 気象庁発表 {e(fmt_dt(q['report_dt']))}</p>")
    for c in q.get("comments", []):
        body.append(f"<p class=safe><strong>{e(c)}</strong></p>")
    if q.get("headline"):
        body.append(f"<p>{e(q['headline'])}</p>")

    rows = [("発生時刻", fmt_dt(q["origin"]) + "ころ")]
    if q["hypo"]:
        rows.append(("震央(震源地)", q["hypo"] + (f"({q['coord']})" if q.get("coord") else "")))
    if q.get("depth"):
        rows.append(("深さ", q["depth"]))
    if q["mag"]:
        rows.append(("規模", f"M{q['mag']}"))
    rows.append(("最大震度", f"震度{int_label(q['maxint'])}" if q["maxint"] else "調査中"))
    body.append(
        "<table>"
        + "".join(f"<tr><th scope=row>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in rows)
        + "</table>"
    )

    blocks = _group_intensity(q.get("obs", []), gran)
    if blocks:
        label = {"city": "市町村", "area": "地域", "pref": "都道府県"}[gran]
        body.append(f"<h2>各地の震度({label}単位・震度の大きい順)</h2>")
        for value, prefs in blocks:
            items = "".join(
                f"<li>{e(p)}" + (f" {e(' '.join(names))}" if names else "") + "</li>"
                for p, names in prefs
            )
            body.append(f"<p><strong>震度{e(int_label(value))}</strong></p><ul>{items}</ul>")
        if gran != "city":
            body.append(
                "<p class=n>観測点が多いため、市町村単位を省略して表示しています。"
                '詳細は<a href="https://www.jma.go.jp/bosai/map.html#contents=earthquake_map">'
                "気象庁</a>で確認してください。</p>"
            )
    else:
        body.append("<p class=n>各地の震度は発表されていません(震源に関する情報等)。</p>")

    body.append('<p><a href="../eq">地震情報の一覧へ</a></p>')
    return "".join(body)


def render_eq_detail(q, generated, banner):
    """地震詳細ページ。予算(gzip 6KB)に収まるまで震度一覧の粒度を段階的に落とす。

    巨大地震では市町村単位の観測が数百件になるため、必要時のみ地域→都道府県へ縮約する。
    """
    title = f"{fmt_dt(q['origin'])}ころの地震"
    html_text = ""
    for gran in ("city", "area", "pref"):
        html_text = page(
            title, _eq_detail_body(q, gran), generated, root="../", banner=banner
        )
        if len(gzip.compress(minify(html_text).encode("utf-8"), 9)) <= EQ_GZIP_BUDGET:
            return html_text
    return html_text


def render_eq(quakes, generated, banner):
    from .parse_eqtsunami import int_label

    body = ["<h1>地震情報</h1>"]
    if not quakes:
        body.append("<p>直近の地震情報はありません。</p>")
    for q in quakes:
        rel = eq_detail_href(q)
        head = (
            f"<strong>{e(fmt_dt(q['origin']))}ころ</strong> {e(q['hypo'])} "
            + (f"M{e(q['mag'])} " if q["mag"] else "")
            + f"最大震度{e(int_label(q['maxint'])) if q['maxint'] else '調査中'}"
        )
        link = f' → <a href="{rel}">各地の震度</a>' if rel else ""
        body.append(
            f"<p>{head}{link}"
            f"<br><small class=n>{e(q['kind'])} / 気象庁発表 {e(fmt_dt(q['report_dt']))}</small></p>"
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
