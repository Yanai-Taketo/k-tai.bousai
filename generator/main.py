"""生成エントリポイント。

長期フィード3本から現在有効な電文集合をステートレスに再構築し、site/ に静的HTMLを生成する。
GitHub Actions・ローカル・VPSのいずれでも同一に動く(ランタイム非依存: decisions.md #15含意)。

使い方: python -m generator.main [--site DIR] [--cache DIR]
終了コード: 0=成功(部分的劣化を含む。詳細はstatus.json)、1=全フィード取得失敗。
"""

import argparse
import datetime
import json
import os
import re
import sys

from . import freshness
from .fetch import FetchError, JmaXmlFeedSource
from .jmautil import JST, parse_dt
from .offices import OFFICES
from .parse_eqtsunami import parse_vtse41, parse_vxse51, parse_vxse53
from .parse_flood import FLOOD_TYPES, merge_office as merge_flood, parse_vxko
from .parse_forecast import parse_vpfd51, parse_vpfw50
from .parse_heat import HEAT_TYPES, is_current as heat_is_current, parse_vpft50
from .parse_sokuho import SOKUHO_TYPES, parse_sokuho
from .parse_typhoon import TYPHOON_TYPES, parse_vptw
from .parse_warnings import WARNING_TYPES, merge_office, parse_vpwwxx
from .render import (
    eq_detail_rel,
    render_about,
    render_eq,
    render_eq_detail,
    render_index,
    render_pref,
    render_tsunami,
    render_typhoon,
    write_page,
)

TELEGRAM_RE = re.compile(r"_(?P<type>[A-Z]{4}\d{2})_(?P<office>\d{6})\.xml$")

HEADERS = """/*
  Cache-Control: public, max-age=60
/status.json
  Cache-Control: no-cache
"""


def classify_entries(entries):
    """フィードentryを (電文種別, 官署コード) 付きで返す。"""
    out = []
    for en in entries:
        m = TELEGRAM_RE.search(en["href"])
        if m:
            out.append((m.group("type"), m.group("office"), en))
    return out


def within(updated, cutoff):
    """フィードのupdated(UTC「Z」表記)がcutoff以降かを日時として比較する。

    文字列比較は不可: フィードは "2026-08-15T08:01:28Z"、cutoffはJSTの
    "+09:00" 表記になるため、同じ時刻でも大小関係が壊れる(実際に台風・
    気象防災速報の24時間判定を誤らせていた)。
    """
    dt = parse_dt(updated)
    return dt is not None and dt >= cutoff


def latest_per_key(classified, types):
    """(種別, 官署) ごとに最新entryを選ぶ。"""
    latest = {}
    for ttype, office, en in classified:
        if ttype not in types:
            continue
        key = (ttype, office)
        if key not in latest or en["updated"] > latest[key]["updated"]:
            latest[key] = en
    return latest


def main(argv=None):
    ap = argparse.ArgumentParser()
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--site", default=os.path.join(base, "site"))
    ap.add_argument("--cache", default=os.path.join(base, ".cache"))
    args = ap.parse_args(argv)

    now = datetime.datetime.now(JST)
    generated = now.strftime("%m月%d日 %H:%M")
    src = JmaXmlFeedSource(args.cache)

    feeds = {}
    feed_updated = {}
    for name in ("extra", "eqvol", "regular"):
        try:
            updated, entries = src.fetch_feed(name)
            feeds[name] = classify_entries(entries)
            feed_updated[name] = updated
        except (FetchError, Exception) as ex:  # noqa: BLE001
            print(f"フィード取得失敗 {name}: {ex}", file=sys.stderr)
            feeds[name] = None
            feed_updated[name] = None

    if all(v is None for v in feeds.values()):
        print("全フィードの取得に失敗。中断します。", file=sys.stderr)
        return 1

    stale = []
    for name, updated in feed_updated.items():
        if updated is None:
            stale.append((name, None))
            continue
        is_stale, age = freshness.check(updated, now)
        if is_stale:
            stale.append((name, age))
    banner = freshness.banner_text(stale)

    anomalies = []
    fetch_errors = []

    # --- 対象電文の選定 ---
    warn_latest = latest_per_key(feeds["extra"] or [], set(WARNING_TYPES))
    sokuho_cutoff = now - datetime.timedelta(hours=24)
    sokuho_entries = [
        (office, en)
        for ttype, office, en in (feeds["extra"] or [])
        if ttype in SOKUHO_TYPES and within(en["updated"], sokuho_cutoff)
    ]
    fc_latest = latest_per_key(feeds["regular"] or [], {"VPFD51", "VPFW50"})

    # 台風: 同一TC(EventID)に複数の電文種別(VPTW60〜65)が出るため、URLの種別+官署でなく
    # 電文の中身(EventID)で束ねる必要がある。ここでは直近24時間分を候補として取得する。
    ty_cutoff = now - datetime.timedelta(hours=24)
    ty_entries = [
        en for ttype, _o, en in (feeds["extra"] or [])
        if ttype in TYPHOON_TYPES and within(en["updated"], ty_cutoff)
    ]
    ty_entries.sort(key=lambda x: x["updated"], reverse=True)
    ty_entries = ty_entries[:40]

    # 指定河川洪水予報(直近24時間)・熱中症警戒アラート(直近36時間。前日17時発表が
    # 翌日いっぱい有効なため窓を広めに取り、対象日で最終判定する)
    flood_entries = [
        (office, en) for ttype, office, en in (feeds["extra"] or [])
        if ttype in FLOOD_TYPES and within(en["updated"], now - datetime.timedelta(hours=24))
    ][:80]
    heat_entries = [
        (office, en) for ttype, office, en in (feeds["extra"] or [])
        if ttype in HEAT_TYPES and within(en["updated"], now - datetime.timedelta(hours=36))
    ][:60]

    eq_entries = [en for t, _o, en in (feeds["eqvol"] or []) if t == "VXSE53"]
    eq51_entries = [en for t, _o, en in (feeds["eqvol"] or []) if t == "VXSE51"]
    ts_entries = [en for t, _o, en in (feeds["eqvol"] or []) if t == "VTSE41"]
    eq_entries.sort(key=lambda x: x["updated"], reverse=True)
    eq51_entries.sort(key=lambda x: x["updated"], reverse=True)
    ts_entries.sort(key=lambda x: x["updated"], reverse=True)

    urls = set()
    urls.update(en["href"] for en in warn_latest.values())
    urls.update(en["href"] for _o, en in sokuho_entries)
    urls.update(en["href"] for en in fc_latest.values())
    urls.update(en["href"] for en in eq_entries[:15])
    urls.update(en["href"] for en in eq51_entries[:3])
    urls.update(en["href"] for en in ts_entries[:1])
    urls.update(en["href"] for en in ty_entries)
    urls.update(en["href"] for _o, en in flood_entries)
    urls.update(en["href"] for _o, en in heat_entries)

    print(f"電文取得: {len(urls)}件")
    telegrams, errors = src.fetch_many(sorted(urls))
    fetch_errors.extend(errors)

    def tel(href):
        return telegrams.get(href)

    # --- 解析: 警報・注意報(官署ごとに7電文を統合) ---
    warn_by_office = {}
    for (ttype, office), en in warn_latest.items():
        data = tel(en["href"])
        if data is None:
            continue
        try:
            p = parse_vpwwxx(data)
            warn_by_office.setdefault(office, []).append(p)
        except Exception as ex:  # noqa: BLE001
            anomalies.append(f"警報電文解析失敗 {ttype}_{office}: {ex}")
    warn_merged = {o: merge_office(ps) for o, ps in warn_by_office.items()}
    for o, m in warn_merged.items():
        anomalies.extend(f"{o}: {a}" for a in m["anomalies"])

    # --- 解析: 気象防災速報(24時間以内・官署ごと) ---
    sokuho_by_office = {}
    sokuho_all = []
    for office, en in sorted(sokuho_entries, key=lambda x: x[1]["updated"], reverse=True):
        data = tel(en["href"])
        if data is None:
            continue
        try:
            s = parse_sokuho(data)
        except Exception as ex:  # noqa: BLE001
            anomalies.append(f"速報電文解析失敗 {office}: {ex}")
            continue
        sokuho_by_office.setdefault(office, []).append(s)
        sokuho_all.append((office, s))

    # --- 解析: 天気予報 ---
    fd_by_office, fw_by_office = {}, {}
    for (ttype, office), en in fc_latest.items():
        data = tel(en["href"])
        if data is None:
            continue
        try:
            if ttype == "VPFD51":
                fd_by_office[office] = parse_vpfd51(data)
            else:
                fw_by_office[office] = parse_vpfw50(data)
        except Exception as ex:  # noqa: BLE001
            anomalies.append(f"予報電文解析失敗 {ttype}_{office}: {ex}")

    # --- 解析: 地震(EventIDで重複排除して10件)・津波 ---
    quakes, seen_events = [], set()
    for en in eq_entries:
        data = tel(en["href"])
        if data is None:
            continue
        try:
            q = parse_vxse53(data)
        except Exception as ex:  # noqa: BLE001
            anomalies.append(f"地震電文解析失敗: {ex}")
            continue
        if q["event_id"] in seen_events:
            continue
        seen_events.add(q["event_id"])
        quakes.append(q)
        if len(quakes) >= 10:
            break
    # 震度速報のみの最新地震(震源・震度がまだ無いもの)を先頭に補う
    for en in eq51_entries[:3]:
        data = tel(en["href"])
        if data is None:
            continue
        try:
            q = parse_vxse51(data)
        except Exception as ex:  # noqa: BLE001
            anomalies.append(f"震度速報解析失敗: {ex}")
            continue
        if q["event_id"] not in seen_events and (
            not quakes or q["report_dt"] > quakes[0]["report_dt"]
        ):
            quakes.insert(0, q)
            seen_events.add(q["event_id"])

    # --- 解析: 指定河川洪水予報(府県ごとに河川単位で統合) ---
    flood_by_office = {}
    for office, en in sorted(flood_entries, key=lambda x: x[1]["updated"]):
        data = tel(en["href"])
        if data is None:
            continue
        try:
            flood_by_office.setdefault(office, []).append(parse_vxko(data))
        except Exception as ex:  # noqa: BLE001
            anomalies.append(f"洪水予報解析失敗 {office}: {ex}")
    floods = {}
    for office, ps in flood_by_office.items():
        rivers = merge_flood(ps)
        if rivers:
            latest = max(ps, key=lambda p: p["report_dt"])
            floods[office] = {
                "rivers": rivers,
                "report_dt": latest["report_dt"],
                "publisher": latest["publisher"],
                "headline": latest["headline"],
            }

    # --- 解析: 熱中症警戒アラート(府県ごとに最新・対象日が過ぎていないもの) ---
    heat_by_office = {}
    for office, en in sorted(heat_entries, key=lambda x: x[1]["updated"]):
        data = tel(en["href"])
        if data is None:
            continue
        try:
            a = parse_vpft50(data)
        except Exception as ex:  # noqa: BLE001
            anomalies.append(f"熱中症アラート解析失敗 {office}: {ex}")
            continue
        if heat_is_current(a, now):
            heat_by_office[office] = a

    # --- 解析: 台風(TCごとに最新の情報番号を採用) ---
    typhoons = {}
    for en in ty_entries:
        data = tel(en["href"])
        if data is None:
            continue
        try:
            t = parse_vptw(data)
        except Exception as ex:  # noqa: BLE001
            anomalies.append(f"台風電文解析失敗: {ex}")
            continue
        eid = t["event_id"]
        prev = typhoons.get(eid)
        if prev is None or t["report_dt"] > prev["report_dt"]:
            typhoons[eid] = t
    typhoon_list = sorted(typhoons.values(), key=lambda t: t["event_id"])

    # 一覧は発生時刻の降順にする(フィード順=発表時刻順のままだと、続報や遠地地震で
    # 発生時刻が前後して読みにくくなる)。発生時刻が無い電文は発表時刻で代替する。
    quakes.sort(key=lambda q: q.get("origin") or q.get("report_dt") or "", reverse=True)

    tsunami = None
    if ts_entries:
        data = tel(ts_entries[0]["href"])
        if data is not None:
            try:
                tsunami = parse_vtse41(data)
            except Exception as ex:  # noqa: BLE001
                anomalies.append(f"津波電文解析失敗: {ex}")

    # --- ページ生成 ---
    os.makedirs(args.site, exist_ok=True)
    sizes = []
    pref_rows = []
    for code, (name, fc_code) in sorted(OFFICES.items()):
        warn = warn_merged.get(code)
        sev = warn["max_severity"] if warn else 0
        pref_rows.append((sev, name, code))
        html_text = render_pref(
            name,
            warn,
            sokuho_by_office.get(code, []),
            fd_by_office.get(fc_code),
            fw_by_office.get(fc_code),
            floods.get(code),
            heat_by_office.get(code),
            generated,
            banner,
        )
        sizes.append(write_page(args.site, f"p/{code}.html", html_text))

    sizes.append(
        write_page(
            args.site,
            "index.html",
            render_index(pref_rows, quakes, tsunami, sokuho_all, typhoon_list, generated, banner),
        )
    )
    sizes.append(write_page(args.site, "eq.html", render_eq(quakes, generated, banner)))
    for q in quakes:
        rel = eq_detail_rel(q)
        if rel:
            sizes.append(
                write_page(args.site, rel, render_eq_detail(q, generated, banner))
            )
    sizes.append(
        write_page(args.site, "tsunami.html", render_tsunami(tsunami, generated, banner))
    )
    sizes.append(
        write_page(args.site, "typhoon.html", render_typhoon(typhoon_list, generated, banner))
    )
    sizes.append(write_page(args.site, "about.html", render_about(generated)))

    with open(os.path.join(args.site, "_headers"), "w") as f:
        f.write(HEADERS)
    with open(os.path.join(args.site, "robots.txt"), "w") as f:
        f.write("User-agent: *\nAllow: /\n")

    status = {
        "generated": now.isoformat(),
        "feeds": feed_updated,
        "stale": [{"feed": n, "age_min": a} for n, a in stale],
        "fetch_errors": len(fetch_errors),
        "anomalies": anomalies[:50],
        "pages": len(sizes),
        "max_gzip_bytes": max(gz for _r, _raw, gz in sizes),
    }
    with open(os.path.join(args.site, "status.json"), "w") as f:
        json.dump(status, f, ensure_ascii=False)

    src.purge_old()
    worst = sorted(sizes, key=lambda s: -s[2])[:5]
    print(f"生成完了: {len(sizes)}ページ / 電文取得失敗 {len(fetch_errors)} / 異常 {len(anomalies)}")
    for rel, raw, gz in worst:
        print(f"  最大級: {rel} raw={raw:,}B gzip={gz:,}B")
    if anomalies:
        for a in anomalies[:10]:
            print(f"  異常: {a}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
