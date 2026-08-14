// フィード更新検知トリガー(設計書§3)。Cloudflare Workers無料枠のCronで毎分実行。
// 気象庁フィードの最新entryが直近90秒以内なら、GitHub Actionsのbuild-deployを起動する。
// ステートレス設計(Workers KVの無料書き込み上限を回避)。多重dispatchはActions側の
// concurrencyが吸収する。

const FEEDS = [
  "https://www.data.jma.go.jp/developer/xml/feed/extra.xml",
  "https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml",
  "https://www.data.jma.go.jp/developer/xml/feed/regular.xml",
];
const FRESH_MS = 90_000;
const UA = "k-tai.bousai-trigger (+https://github.com/Yanai-Taketo/k-tai.bousai)";

async function latestEntryUpdated(url) {
  const r = await fetch(url, { headers: { "User-Agent": UA } });
  if (!r.ok) return null;
  const text = await r.text();
  // 最初の<entry>内の<updated> = 最新電文の時刻(フィード自体の<updated>は毎分更新のため使わない)
  const m = text.match(/<entry>[\s\S]*?<updated>([^<]+)<\/updated>/);
  return m ? Date.parse(m[1]) : null;
}

export default {
  async scheduled(_event, env, _ctx) {
    let fresh = false;
    for (const url of FEEDS) {
      try {
        const t = await latestEntryUpdated(url);
        if (t && Date.now() - t < FRESH_MS) {
          fresh = true;
          break;
        }
      } catch (_e) {
        // 個別フィードの失敗は無視(次のフィードへ)。全滅時はdispatchせず、
        // Actions側の5分cronがフォールバックする。
      }
    }
    if (!fresh) return;
    const repo = env.GITHUB_REPO; // 例: "Yanai-Taketo/k-tai.bousai"
    await fetch(
      `https://api.github.com/repos/${repo}/actions/workflows/build-deploy.yml/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "User-Agent": UA,
          "X-GitHub-Api-Version": "2022-11-28",
        },
        body: JSON.stringify({ ref: env.GITHUB_BRANCH || "main" }),
      },
    );
  },
};
