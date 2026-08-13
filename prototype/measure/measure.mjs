// 128kbps級低速回線での表示時間・転送量の実測ハーネス。
// Chromium DevTools Protocol の Network.emulateNetworkConditions で
// 帯域 16,000 bytes/s(=128kbps)・往復遅延 300ms を模擬し、
// プロトタイプと既存防災サイトの表示完了時間・転送量を比較する。
//
// 実行: node measure.mjs [--quick]
// 前提: プロトタイプを http://127.0.0.1:8123 で配信しておくこと
//       (python3 -m http.server 8123 --directory ../site)

import { chromium } from "playwright";

const TARGETS = [
  { name: "プロトタイプ トップ", url: "http://127.0.0.1:8123/index.html", local: true },
  { name: "プロトタイプ 宮城県警報", url: "http://127.0.0.1:8123/warn/040000.html", local: true },
  { name: "気象庁 防災ポータル", url: "https://www.jma.go.jp/bosai/" },
  { name: "気象庁 キキクル(危険度分布)", url: "https://www.jma.go.jp/bosai/risk/" },
  { name: "重ねるハザードマップ", url: "https://disaportal.gsi.go.jp/maps/index.html" },
  { name: "tenki.jp トップ", url: "https://tenki.jp/" },
  { name: "Yahoo!天気 警報・注意報", url: "https://typhoon.yahoo.co.jp/weather/jp/warn/" },
];

// 128kbps = 16,000 bytes/s。RTT300msは応急復旧回線・輻輳時を想定した控えめな値。
const THROTTLE = { offline: false, latency: 300, downloadThroughput: 16000, uploadThroughput: 16000 };
const TIMEOUT_THROTTLED = 180_000; // 3分で打ち切り(打ち切り時は転送済みバイトを記録)
const TIMEOUT_FULL = 90_000;

const proxyServer = process.env.HTTPS_PROXY || process.env.https_proxy || null;

async function measureOnce(browser, target, throttle) {
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
  if (throttle) await cdp.send("Network.emulateNetworkConditions", THROTTLE);

  let bytes = 0;
  let requests = 0;
  cdp.on("Network.loadingFinished", (ev) => { bytes += ev.encodedDataLength || 0; });
  cdp.on("Network.requestWillBeSent", () => { requests += 1; });

  const timeout = throttle ? TIMEOUT_THROTTLED : TIMEOUT_FULL;
  const start = Date.now();
  let loadMs = null;
  let fcpMs = null;
  let status = "完了";
  try {
    await page.goto(target.url, { waitUntil: "load", timeout });
    loadMs = Date.now() - start;
    fcpMs = await page
      .evaluate(() => {
        const e = performance.getEntriesByName("first-contentful-paint");
        return e.length ? Math.round(e[0].startTime) : null;
      })
      .catch(() => null);
    // load後の遅延読み込み分を1秒だけ待って計上
    await page.waitForTimeout(1000);
  } catch {
    status = `未完了(${Math.round((Date.now() - start) / 1000)}秒で打ち切り)`;
  }
  await context.close();
  return { bytes, requests, loadMs, fcpMs, status };
}

function fmtBytes(n) {
  if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(2) + " MB";
  if (n >= 1024) return (n / 1024).toFixed(1) + " KB";
  return n + " B";
}
function fmtMs(n) {
  return n == null ? "—" : (n / 1000).toFixed(1) + " 秒";
}

const quick = process.argv.includes("--quick");
const browser = await chromium.launch({
  executablePath: "/opt/pw-browsers/chromium",
  proxy: proxyServer ? { server: proxyServer, bypass: "127.0.0.1,localhost" } : undefined,
  // 計測環境のTLS終端プロキシがTLS1.3のClientHelloを処理できないため1.2に固定。
  // 全ターゲットを同条件で計測するので比較には影響しない。
  args: proxyServer ? ["--ssl-version-max=tls1.2"] : [],
});

const results = [];
for (const t of TARGETS) {
  process.stderr.write(`計測中(通常回線): ${t.name}\n`);
  const full = await measureOnce(browser, t, false);
  let slow = null;
  if (!quick) {
    process.stderr.write(`計測中(128kbps+RTT300ms): ${t.name}\n`);
    slow = await measureOnce(browser, t, true);
  }
  results.push({ ...t, full, slow });
  console.log(JSON.stringify({ name: t.name, full, slow }));
}
await browser.close();

console.log("\n| サイト | 転送量 | リクエスト数 | 128kbps 表示完了 | 128kbps 初回描画 |");
console.log("|---|---|---|---|---|");
for (const r of results) {
  const s = r.slow || {};
  const loadCell = s.status === "完了" ? fmtMs(s.loadMs) : (s.status || "—") + "(" + fmtBytes(s.bytes || 0) + "転送)";
  console.log(
    `| ${r.name} | ${fmtBytes(r.full.bytes)} | ${r.full.requests} | ${loadCell} | ${fmtMs(s.fcpMs)} |`
  );
}
