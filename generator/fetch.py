"""フィード・電文の取得層。

- 気象庁防災情報XML PULL型の長期フィードを取得し、entry一覧に変換する。
- 電文XMLは一度発行されると不変のため、URL名でディスクキャッシュする。
- 取得元はSourceクラスに閉じ、将来のDMDATA移行時はクラスの差し替えで対応する
  (decisions.md #3・#15の含意)。
"""

import concurrent.futures
import gzip
import os
import ssl
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

UA = "k-tai.bousai generator (+https://github.com/Yanai-Taketo/k-tai.bousai)"
ATOM = "{http://www.w3.org/2005/Atom}"

FEEDS = {
    "extra": "https://www.data.jma.go.jp/developer/xml/feed/extra_l.xml",
    "eqvol": "https://www.data.jma.go.jp/developer/xml/feed/eqvol_l.xml",
    "regular": "https://www.data.jma.go.jp/developer/xml/feed/regular_l.xml",
}


class FetchError(Exception):
    pass


class JmaXmlFeedSource:
    """気象庁防災情報XML(無償・ベストエフォート)からの取得。"""

    def __init__(self, cache_dir):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        cafile = os.environ.get("SSL_CERT_FILE")
        if cafile and os.path.exists(cafile):
            self.ctx = ssl.create_default_context(cafile=cafile)
        else:
            self.ctx = ssl.create_default_context()

    def _get(self, url, timeout=30, retries=2):
        last = None
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"}
                )
                with urllib.request.urlopen(req, timeout=timeout, context=self.ctx) as r:
                    data = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        data = gzip.decompress(data)
                    return data
            except (urllib.error.URLError, OSError, TimeoutError) as ex:
                last = ex
                if attempt < retries:
                    time.sleep(2 * (attempt + 1))
        raise FetchError(f"{url}: {last}")

    def fetch_feed(self, name):
        """フィードを取得し (updated ISO文字列, entry辞書リスト) を返す。"""
        data = self._get(FEEDS[name])
        root = ET.fromstring(data)
        entries = []
        for en in root.findall(f"{ATOM}entry"):
            link = en.find(f"{ATOM}link")
            entries.append(
                {
                    "title": (en.findtext(f"{ATOM}title") or "").strip(),
                    "updated": (en.findtext(f"{ATOM}updated") or "").strip(),
                    "href": link.get("href") if link is not None else "",
                }
            )
        updated = (root.findtext(f"{ATOM}updated") or "").strip()
        return updated, entries

    def fetch_telegram(self, url):
        """電文XMLを取得する(不変なのでディスクキャッシュ)。"""
        path = os.path.join(self.cache_dir, url.rsplit("/", 1)[-1])
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        data = self._get(url)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        return data

    def purge_old(self, days=8):
        """長期フィードの収録期間(7日)より古いキャッシュ電文を削除する。"""
        cutoff = time.time() - days * 86400
        removed = 0
        for name in os.listdir(self.cache_dir):
            path = os.path.join(self.cache_dir, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError:
                pass
        return removed

    def fetch_many(self, urls, workers=16):
        """複数電文を並列取得し {url: bytes} と失敗一覧を返す。"""
        results, errors = {}, []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(self.fetch_telegram, u): u for u in urls}
            for fut in concurrent.futures.as_completed(futs):
                url = futs[fut]
                try:
                    results[url] = fut.result()
                except Exception as err:  # noqa: BLE001 - 個別失敗は集約して報告
                    errors.append((url, str(err)))
        return results, errors
