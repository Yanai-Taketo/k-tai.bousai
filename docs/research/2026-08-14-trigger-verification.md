# 毎分トリガーの「GitHub ActionsのみでのAPIキーレス化」検証記録

依頼者からの「毎分トリガーもGitHub ActionsならAPIキー(PAT)不要にできるのでは。
自分の情報を鵜呑みにせず敵対的意見も取り入れて判断してほしい」という提起を受け、
公式ドキュメントでの事実検証(3エージェント)と、賛成派・反対派の敵対的討論
(2エージェント)を実施した記録。すべての主張に一次資料の出典を付す。

## 1. 検証済みの事実

### GitHub Actions schedule の制約

| 事実 | 判定 | 出典 |
|------|------|------|
| scheduleの最短間隔は**5分**。毎分cron(`* * * * *`)はエラーにならず黙って5分間隔として扱われる | 公式明記 | [Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)、[2019-11-01 changelog](https://github.blog/changelog/2019-11-01-github-actions-scheduled-jobs-maximum-frequency-is-changing/) |
| scheduleは高負荷時に**遅延**するだけでなく、負荷が十分高いと**ドロップ(スキップ)される**。毎時0分が高負荷帯と公式に名指し | 公式明記 | 同上 |
| 実測の遅延は5〜30分が常態、4時間超のドリフト報告もある(公式SLAなし) | コミュニティ報告 | GitHub Community [#156282](https://github.com/orgs/community/discussions/156282)、[#196910](https://github.com/orgs/community/discussions/196910) |
| 公開リポジトリでは**60日間リポジトリ活動が無いとscheduledワークフローが自動無効化**される | 公式明記 | [同上](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)、[Disabling and enabling a workflow](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/disabling-and-enabling-a-workflow) |
| 「活動」の公式定義はない。schedule実行自体は活動に数えられず、**デフォルトブランチへのcommit(botでも可)でリセット**されるというのが実証ベースの通説 | 実証ベース | [efrecon/gh-action-keepalive](https://github.com/efrecon/gh-action-keepalive) ほか |
| 無効化は**ワークフローファイル単位**。scheduleとworkflow_dispatchを同一ファイルに置くと、無効化時にdispatchも「Cannot trigger a 'workflow_dispatch' on a disabled workflow」で**道連れ**になる | 公式仕様+実例 | [upptime #593](https://github.com/orgs/upptime/discussions/593)、[benc-uk/workflow-dispatch #72](https://github.com/benc-uk/workflow-dispatch/issues/72) |

### 認証・トークン

| 事実 | 判定 | 出典 |
|------|------|------|
| GITHUB_TOKENが起こしたイベントは新しいランを作らない規則には例外があり、**workflow_dispatch / repository_dispatch は必ずランを作る**。つまり同一リポジトリ内のワークフロー連鎖はPAT不要(`permissions: actions: write`のみ) | 公式明記 | [Triggering a workflow from a workflow](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow) |
| **リポジトリ外部**(Cloudflare Worker等)からworkflow_dispatchを起動する**無認証の経路は存在しない**(読み取り系エンドポイントにはある「without authentication」の明記がdispatchには無い。write権限付きトークン必須) | 公式仕様 | [Create a workflow dispatch event](https://docs.github.com/en/rest/actions/workflows?apiVersion=2022-11-28#create-a-workflow-dispatch-event) |
| fine-grained PAT(単一リポジトリ・Actions: Read and writeのみ)が漏えいしても**コードpush・Secrets読み出し・ワークフローファイル改変は不可能**(それぞれContents/Secrets/Workflowsの別権限)。可能なのは妨害系のみ: run cancel、workflow disable、不要起動、ログ・アーティファクト削除、**OIDC subject claim書き換え**(GitHub PagesのOIDCデプロイ妨害が可能) | 公式権限表 | [Permissions required for fine-grained PATs](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens) |

### 利用制限・規約

| 事実 | 判定 | 出典 |
|------|------|------|
| 公開リポジトリの標準ランナーはActions利用分数**無料**(「無制限」の文言はなく、各種利用制限は適用) | 公式明記 | [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) |
| ジョブ最大**6時間**で強制終了。同時実行ジョブFree 20 | 公式明記 | [Actions limits](https://docs.github.com/en/actions/reference/limits) |
| Actions利用規約は「**serverless applicationの一部としての利用**」「サーバー負担が利用者利益に不釣り合いな活動」を禁止し、違反時はジョブ強制終了→利用制限→リポジトリ無効化→アカウント停止の段階的措置を明記。常時ポーリングループ(約720ランナー時間/月の占有)はこの例示に構造的に近い**グレーゾーン** | 公式規約 | [GitHub Terms - Actions](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features#actions) |
| Cloudflare Workers無料枠のCronは**毎分実行が公式サポート範囲**(cron例として`* * * * *`明記)。毎分=1,440回/日は無料枠10万リクエスト/日の約1.4% | 公式明記 | [Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/)、[Workers limits](https://developers.cloudflare.com/workers/platform/limits/) |

## 2. 敵対的討論の要旨

**キーレス派(Actionsのみ)の最強の論点**: 保存秘密ゼロは「リスクの縮小」でなく「消滅」。
PAT失効は「5分フォールバックへの静かな劣化」でGitHub側に何のエラーも出ず、無人運用では
誰も気づかない——サイレント劣化は防災システムで最も危険な故障モード。また現行設計が
scheduleとdispatch受け口を同一ファイルに置いているのは60日無効化の道連れ地雷である。

**現行維持派(Worker+PAT)の最強の論点**: 対抗案は要件を満たさない。5分scheduleのみ案は
「最短5分」の公式仕様で反映2〜4分目標が原理的に未達なうえ、遅延・ドロップ・60日無効化を
抱える。GITHUB_TOKEN自己チェーン案は技術的には成立するが、規約グレーゾーンに「止まっては
ならない防災インフラ」を置く自己矛盾であり、チェーン断絶は「何も起きない」という観測不能な
障害モードを生む。Cloudflare毎分Cron+workflow_dispatchは両プラットフォームの公式サポート
範囲内で要件を満たす唯一の構成。

**両者が一致した点**: (1) 勝敗にかかわらず、schedule/dispatchのワークフローファイル分離、
keepaliveコミット、トリガー死活の外形監視は直ちに実施すべき。(2) 長期秘密の理想形は
PATでなくGitHub App(installation tokenの都度発行)への移行。

## 3. 結論(決定#20)

**現行のCloudflare Worker毎分Cron+fine-grained PAT+workflow_dispatch構成を維持する。**
「GitHub ActionsのみでAPIキーレス」は、外部からの無認証起動が存在しない以上、
scheduleの5分制限(反映目標未達)か規約グレーの常時ループかの二択にしかならず、
防災用途の可用性要件と両立しない。PATリスクは権限表で実害範囲が画定でき
(コード改竄・Secrets窃取は不可能)、監視で検知可能な既知のリスクとして管理する。

討論で確定した堅牢化3点を実装済み:

1. **ワークフローファイル分離**: `build-deploy.yml`をworkflow_dispatch専用にし、
   5分フォールバックは`fallback-schedule.yml`(GITHUB_TOKENでdispatch)へ分離。
   60日無効化が起きても止まるのはフォールバックのみ。cron分を毎時0分からオフセット。
2. **keepaliveコミット**: `monitor.yml`が最終コミットから30日経過を検知したら
   keepaliveファイルを自動コミットし、60日不活性を構造的に防止。
3. **毎分トリガーの死活検知**: `monitor.yml`が「直近24時間にworkflow_dispatch起動ゼロ」
   を異常としてIssue起票(Variable `MINUTE_TRIGGER=1`設定後に有効)。Worker側も
   dispatch失敗をログに記録。PAT失効の静かな劣化を最長24時間で検知する。

将来オプション: GitHub App化(長期秘密をApp秘密鍵に集約し、installation tokenを
都度発行)。運用開始後の改善課題とする。
