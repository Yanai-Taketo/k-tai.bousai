"""フィード鮮度の判定(要件R-4・N-11)。

気象庁の長期フィードは毎時更新・高頻度フィード相当の<updated>を持つ。
更新が閾値を超えて停滞している場合、ページに劣化警告を出す。
"""

from .jmautil import parse_dt

STALE_MINUTES = 90  # 長期フィードは毎時更新のため、90分無更新で停滞とみなす


def check(feed_updated_iso, now, limit_minutes=STALE_MINUTES):
    """(停滞しているか, 経過分) を返す。updatedが読めない場合は停滞扱い。"""
    dt = parse_dt(feed_updated_iso)
    if dt is None:
        return True, None
    age = (now - dt).total_seconds() / 60
    return age > limit_minutes, int(age)


def banner_text(stale_feeds):
    """劣化警告文。stale_feeds: [(フィード名, 経過分 or None)]"""
    if not stale_feeds:
        return ""
    worst = max((m or 999) for _n, m in stale_feeds)
    return (
        f"注意: 気象庁からのデータ取得が約{worst}分間更新されていません。"
        "このページの情報は最新でない可能性があります。最新の情報は"
        '<a href="https://www.jma.go.jp/bosai/">気象庁ホームページ</a>や'
        "テレビ・ラジオで確認してください。"
    )
