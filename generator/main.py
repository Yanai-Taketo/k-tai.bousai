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
from .jmautil import JST
from .offices import OFFICES
from .parse_eqtsunami import parse_vtse41, parse_vxse51, parse_vxse53
from .parse_forecast import parse_vpfd51, parse_vpfw50
from .parse_sokuho import SOKUHO_TYPES, parse_sokuho
from .parse_warnings import WARNING_TYPES, merge_office, parse_vpwwxx
from .render import (
    render_about,
    render_eq,
    render_index,
    render_pref,
    render_tsunami,
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
    sokuho_cutoff = (now - datetime.timedelta(hours=24)).isoformat()
    sokuho_entries = [
        (office, en)
        for ttype, office, en in (feeds["extra"] or [])
        if ttype in SOKUHO_TYPES and en["updated"] >= sokuho_cutoff
    ]
    fc_latest = latest_per_key(feeds["regular"] or [], {"VPFD51", "VPFW50"})

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
            generated,
            banner,
        )
        sizes.append(write_page(args.site, f"p/{code}.html", html_text))

    pref_rows.sort(key=lambda r: (-r[0], r[2]))
    sizes.append(
        write_page(
            args.site,
            "index.html",
            render_index(pref_rows, quakes, tsunami, sokuho_all, generated, banner),
        )
    )
    sizes.append(write_page(args.site, "eq.html", render_eq(quakes, generated, banner)))
    sizes.append(
        write_page(args.site, "tsunami.html", render_tsunami(tsunami, generated, banner))
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
