// フィード更新検知トリガー(設計書§3)。Cloudflare Workers無料枠のCronで毎分実行。
//
// 判定方式(2026-08-15改訂): 「最新電文の時刻 > 前回ビルドの開始時刻」なら起動する。
// 生成はステートレスな全再生成なので、ある電文より後に始まったビルドにはその電文が
// 必ず含まれる。したがってこの比較だけで、取りこぼしも重複起動も生じない。
//
// 旧方式(最新entryが90秒以内なら起動)は失敗だった。実測ではフィードに電文が現れる
// のは<updated>から約75秒後で、毎分ポーリングでは75〜90秒の窓に当たった時しか発火せず、
// 直近12回の更新のうちWorker由来は1回だけだった(残りはGitHub側の不安定なcron頼み)。
//
// 併せて下限保証を持たせる: 前回ビルドから MAX_STALE_MS を超えたら無条件で起動する。
// GitHub Actionsのscheduleは実測で到達率12%(5分毎の設計が実質23〜80分毎)のため、
// フォールバックをGitHub側に頼らず、確実に動くCloudflare Cron側で担保する。

const FEEDS = [
  "https://www.data.jma.go.jp/developer/xml/feed/extra.xml",
  "https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml",
  "https://www.data.jma.go.jp/developer/xml/feed/regular.xml",
];
const MAX_STALE_MS = 10 * 60_000; // 前回ビルドからこれを超えたら無条件で起動
const FALLBACK_FRESH_MS = 5 * 60_000; // GitHub API障害時に使う保険の鮮度窓
const WORKFLOW = "build-deploy.yml";
const UA = "k-tai.bousai-trigger (+https://github.com/Yanai-Taketo/k-tai.bousai)";

function ghHeaders(env) {
  return {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: "application/vnd.github+json",
    "User-Agent": UA,
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

async function latestEntryUpdated(url) {
  // 最初の<entry>内の<updated> = 最新電文の時刻(フィード自体の<updated>は別物なので使わない)
  const r = await fetch(url, { headers: { "User-Agent": UA } });
  if (!r.ok) return null;
  const m = (await r.text()).match(/<entry>[\s\S]*?<updated>([^<]+)<\/updated>/);
  return m ? Date.parse(m[1]) : null;
}

async function lastBuildStartedAt(env) {
  // 直近のbuild-deploy実行の開始時刻。取得できなければnull(呼び出し側で保険に切替)。
  const r = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${WORKFLOW}/runs?per_page=1`,
    { headers: ghHeaders(env) },
  );
  if (!r.ok) {
    console.error(`実行履歴の取得に失敗: HTTP ${r.status}`);
    return null;
  }
  const runs = (await r.json()).workflow_runs;
  if (!runs || runs.length === 0) return 0; // 一度も走っていない → 起動する
  return Date.parse(runs[0].created_at);
}

async function dispatch(env, reason) {
  const r = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: ghHeaders(env),
      body: JSON.stringify({ ref: env.GITHUB_BRANCH || "main" }),
    },
  );
  if (r.ok) {
    console.log(`起動しました (${reason})`);
  } else {
    // 401/403=PAT失効・権限不足、404/422=ワークフロー無効化等。
    // リポジトリ側でも monitor.yml が「24時間dispatchなし」で検知しIssueを起票する。
    console.error(`起動に失敗: HTTP ${r.status} ${await r.text()}`);
  }
}

export default {
  async scheduled(_event, env, _ctx) {
    const now = Date.now();

    const updates = await Promise.all(
      FEEDS.map((u) => latestEntryUpdated(u).catch(() => null)),
    );
    const newest = Math.max(0, ...updates.filter((t) => t !== null));

    const lastBuild = await lastBuildStartedAt(env);

    if (lastBuild === null) {
      // GitHub APIが読めない場合の保険。窓を広めに取り、取りこぼしより重複を許容する
      // (重複はActions側のconcurrencyが直列化して吸収する)。
      if (newest && now - newest < FALLBACK_FRESH_MS) {
        await dispatch(env, "保険: 実行履歴を取得できず、新しい電文あり");
      }
      return;
    }

    if (newest > lastBuild) {
      await dispatch(env, `新着電文 (${new Date(newest).toISOString()})`);
      return;
    }

    if (now - lastBuild > MAX_STALE_MS) {
      await dispatch(env, `下限保証: 前回ビルドから${Math.round((now - lastBuild) / 60000)}分経過`);
    }
  },
};
