// トリガー判定のテスト。node --test で実行(依存なし)。
//
// この判定は一度壊れても誰も気づかないまま「GitHubの不安定なcron頼み」に静かに
// 劣化する(実際に2026-08-15までそうなっていた)。実測で確認した以下の性質を
// 回帰テストとして固定する:
//   - 気象庁フィードに電文が現れるのは<updated>から約75〜120秒後
//   - したがって「N秒以内なら新着」という鮮度窓での判定は取りこぼす
//   - 正しい判定は「最新電文の時刻 > 前回ビルドの開始時刻」

import assert from "node:assert/strict";
import test from "node:test";

import worker from "./index.js";

const ENV = {
  GITHUB_REPO: "Yanai-Taketo/k-tai.bousai",
  GITHUB_BRANCH: "main",
  GITHUB_TOKEN: "dummy",
};

/** fetchを差し替えて1回実行し、dispatchされたかを返す。 */
async function run({ entryUpdated, lastRunCreated, runsApiOk = true }) {
  const calls = [];
  const feedXml = (t) =>
    `<feed><updated>${t}</updated><entry><title>x</title>` +
    `<updated>${t}</updated></entry></feed>`;

  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), method: init?.method || "GET" });
    if (String(url).includes("/dispatches")) {
      return new Response(null, { status: 204 });
    }
    if (String(url).includes("/runs?")) {
      if (!runsApiOk) return new Response("boom", { status: 500 });
      const body =
        lastRunCreated === null
          ? { workflow_runs: [] }
          : { workflow_runs: [{ created_at: new Date(lastRunCreated).toISOString() }] };
      return new Response(JSON.stringify(body), { status: 200 });
    }
    return new Response(feedXml(new Date(entryUpdated).toISOString()), { status: 200 });
  };

  await worker.scheduled(null, ENV, null);
  return calls.some((c) => c.url.includes("/dispatches") && c.method === "POST");
}

const MIN = 60_000;

test("前回ビルドより新しい電文があれば起動する", async () => {
  const now = Date.now();
  assert.equal(
    await run({ entryUpdated: now - 2 * MIN, lastRunCreated: now - 5 * MIN }),
    true,
  );
});

test("フィード配信の遅れ(実測75〜120秒)があっても取りこぼさない", async () => {
  // 旧実装は「90秒以内」でのみ起動したため、120秒遅れて現れた電文を落としていた。
  const now = Date.now();
  assert.equal(
    await run({ entryUpdated: now - 120_000, lastRunCreated: now - 4 * MIN }),
    true,
    "120秒前の電文が前回ビルドより新しければ起動しなければならない",
  );
});

test("前回ビルド以降に新着がなければ起動しない(重複ビルドを避ける)", async () => {
  const now = Date.now();
  assert.equal(
    await run({ entryUpdated: now - 8 * MIN, lastRunCreated: now - 3 * MIN }),
    false,
  );
});

test("新着がなくても前回ビルドから10分超なら起動する(下限保証)", async () => {
  const now = Date.now();
  assert.equal(
    await run({ entryUpdated: now - 30 * MIN, lastRunCreated: now - 11 * MIN }),
    true,
    "GitHubのscheduleは到達率が低いため、下限保証はCloudflare側で担保する",
  );
});

test("一度もビルドされていなければ起動する", async () => {
  const now = Date.now();
  assert.equal(await run({ entryUpdated: now - 30 * MIN, lastRunCreated: null }), true);
});

test("GitHub APIが落ちている場合は鮮度窓で保険的に起動する", async () => {
  const now = Date.now();
  assert.equal(
    await run({ entryUpdated: now - 2 * MIN, lastRunCreated: 0, runsApiOk: false }),
    true,
    "実行履歴が読めなくても、新しい電文があれば起動する(取りこぼしより重複を許容)",
  );
  assert.equal(
    await run({ entryUpdated: now - 60 * MIN, lastRunCreated: 0, runsApiOk: false }),
    false,
    "古い電文しかない場合は起動しない(無限に起動し続けない)",
  );
});
