#!/usr/bin/env python3
"""死活・鮮度監視(設計書§6)。標準ライブラリのみ。

確認項目:
  1. 気象庁フィード(extra.xml)が到達可能で、フィード<updated>が30分以内。
  2. SITE_URLS(カンマ区切りの公開URL)それぞれについて、
     /status.json の generated が45分以内、かつ / がHTTP 200。
異常が1つでもあれば終了コード1(GitHub Actionsが失敗となり通知される)。
"""

import datetime
import json
import os
import re
import sys
import urllib.request

FEED = "https://www.data.jma.go.jp/developer/xml/feed/extra.xml"
UA = "k-tai.bousai monitor"
FEED_LIMIT_MIN = 30
SITE_LIMIT_MIN = 45


def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def age_minutes(iso):
    dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - dt).total_seconds() / 60


def main():
    failures = []

    try:
        _st, data = get(FEED)
        m = re.search(rb"<updated>([^<]+)</updated>", data)
        if not m:
            failures.append("フィード: <updated>が見つからない")
        else:
            age = age_minutes(m.group(1).decode())
            if age > FEED_LIMIT_MIN:
                failures.append(f"フィード: {age:.0f}分間更新なし(閾値{FEED_LIMIT_MIN}分)")
            else:
                print(f"OK フィード更新 {age:.0f}分前")
    except Exception as ex:  # noqa: BLE001
        failures.append(f"フィード取得失敗: {ex}")

    urls = [u.strip().rstrip("/") for u in os.environ.get("SITE_URLS", "").split(",") if u.strip()]
    if not urls:
        print("SITE_URLS未設定のため公開サイトの確認はスキップ")
    for base in urls:
        try:
            st, body = get(f"{base}/status.json")
            gen = json.loads(body)["generated"]
            age = age_minutes(gen)
            if age > SITE_LIMIT_MIN:
                failures.append(f"{base}: 生成が{age:.0f}分前(閾値{SITE_LIMIT_MIN}分)")
            else:
                print(f"OK {base} 生成 {age:.0f}分前")
            st2, _ = get(f"{base}/")
            if st2 != 200:
                failures.append(f"{base}/: HTTP {st2}")
        except Exception as ex:  # noqa: BLE001
            failures.append(f"{base}: {ex}")

    for f in failures:
        print(f"NG {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
