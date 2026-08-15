// 現行サイトの表示時間を128kbps級の低速回線で実測する。
// READMEに載せている数値はこのスクリプトで取得したもの。
//
// 使い方:
//   python3 -m generator.main --site /tmp/site        # サイトを生成
//   (cd /tmp/site && python3 -m http.server 8123 &)   # ローカル配信
//   node measure-site.mjs                             # 計測
//
// 注意: python3 -m http.server は gzip 圧縮しないため、転送量は非圧縮値になる。
// 実環境(Cloudflare Pages / GitHub Pages)はgzip/brotliで配信するので、
// ここで出る数値は実環境より不利な(遅い)側に振れる。
//
// 既存の measure.mjs はフェーズ0のプロトタイプと他社サイトを比較するもので、
// 対象が異なる(あちらは凍結、こちらが現行サイト用)。

import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:8123";

// 128kbps = 16,000 bytes/s。RTT300msは輻輳時・応急復旧回線を想定した控えめな値。
const THROTTLE = {
  offline: false,
  latency: 300,
  downloadThroughput: 16000,
  uploadThroughput: 16000,
};

// 地震詳細は日々URLが変わるため、一覧から最初のリンクを拾って対象に加える。
const PAGES = [
  ["トップ", "/index.html"],
  ["府県(東京)", "/p/130000.html"],
  ["地震一覧", "/eq.html"],
  ["台風", "/typhoon.html"],
  ["津波", "/tsunami.html"],
  ["このサイトについて", "/about.html"],
];

const browser = await chromium.launch(
  process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {},
);

async function measure(name, path) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", THROTTLE);
  let bytes = 0;
  cdp.on("Network.loadingFinished", (e) => {
    bytes += e.encodedDataLength || 0;
  });
  const t0 = Date.now();
  try {
    await page.goto(BASE + path, { waitUntil: "load", timeout: 60000 });
  } catch (e) {
    console.error(`  ${name}: 読み込み失敗 ${e.message}`);
  }
  const ms = Date.now() - t0;
  await ctx.close();
  return { name, ms, bytes };
}

// 地震詳細ページを一覧から探す
try {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(BASE + "/eq.html", { timeout: 20000 });
  const href = await page.getAttribute('a[href^="eq/"]', "href");
  if (href) PAGES.splice(3, 0, ["地震詳細", "/" + href + ".html"]);
  await ctx.close();
} catch {
  console.error("(地震詳細ページの特定をスキップ)");
}

console.log(`対象: ${BASE} / 128kbps・RTT300ms・キャッシュ無効`);
console.log("ページ".padEnd(20) + "表示完了".padStart(9) + "転送量(非圧縮)".padStart(16));
for (const [name, path] of PAGES) {
  const r = await measure(name, path);
  console.log(
    r.name.padEnd(20) +
      `${r.ms}ms`.padStart(9) +
      `${r.bytes.toLocaleString()}B`.padStart(16),
  );
}
await browser.close();
