# 設計書 — 文字中心・軽量防災サイト(フェーズ1)

- 作成日: 2026-08-14
- 前提: [要件定義書](requirements.md)、[意思決定記録](decisions.md) #1〜#15
- 対応する決定: ホスティング=案A「Cloudflare Pages+GitHub Pagesのみで完結」(#15)、ランタイム非依存の生成系(#12含意)

## 1. 全体アーキテクチャ

```mermaid
flowchart LR
    subgraph JMA["気象庁(上流・AWS系)"]
      FEED["防災情報XML Atomフィード<br>S3+CloudFront / max-age=60"]
    end
    subgraph TRIG["起動トリガー(二重化)"]
      CFW["Cloudflare Workers Cron<br>毎分: フィード更新検知→dispatch"]
      CRON["GitHub Actions schedule<br>5分毎(フォールバック)"]
    end
    subgraph GH["GitHub Actions(生成・デプロイ)"]
      GEN["fetch → parse → generate<br>(静的HTML一式)"]
    end
    subgraph SERVE["配信(異系統2系統)"]
      CFP["Cloudflare Pages<br>(主系・独自ドメイン)"]
      GHP["GitHub Pages<br>(ミラー)"]
    end
    FEED -->|"条件付きGET"| CFW
    FEED --> GEN
    CFW -->|workflow_dispatch| GEN
    CRON --> GEN
    GEN -->|"wrangler pages deploy<br>(直接アップロード)"| CFP
    GEN -->|"actions/deploy-pages<br>(artifact方式・コミットなし)"| GHP
```

障害点の整理(#15の意図に対応):

| 部位 | 落ちたときの挙動 |
|---|---|
| 上流フィード(AWS) | 生成は前回内容を維持。フィード停滞を検知し劣化警告を自動掲出(R-4) |
| GitHub(Actions) | **更新のみ停止**。配信は2系統とも継続、取得時刻表示(R-1)が鮮度の受け皿 |
| Cloudflare Pages | GitHub Pagesミラーで閲覧可能(逆も同様)。上流がAWS系のため配信面にAWS系を使わない |
| Workers Cronトリガー | Actions schedule(5分毎)が拾う。反映が最大+5分遅れるだけ |

## 2. リポジトリ・成果物構成

```
generator/          # 生成システム(Python 3.11+, 標準ライブラリのみ。プロトタイプを発展)
  fetch.py          #   フィード・電文取得(条件付きGET、リトライ、ソース差し替え可能I/F)
  parse/            #   電文種別ごとのパーサ(警報・地震・津波・天気予報)
  render/           #   中間モデル→HTMLテンプレート(手書き最小テンプレート)
  freshness.py      #   フィード<updated>停滞検知 → 劣化警告フラグ
  main.py           #   一括実行エントリ(ローカル/Actions/将来のVPSで同一動作)
site/               # 生成物(Actionsのartifactとしてのみ存在。リポジトリにはコミットしない)
worker/             # Cloudflare Workers Cronトリガー(フィード更新検知→workflow_dispatch)
.github/workflows/
  build-deploy.yml  # 生成+2系統デプロイ(workflow_dispatch + schedule 5分毎)
  monitor.yml       # 死活・鮮度監視(15分毎)
prototype/          # フェーズ0の実証コード(参照用に凍結)
```

- 生成物はコミットしない(履歴肥大の回避)。GitHub Pagesへはartifact方式(`actions/upload-pages-artifact`+`actions/deploy-pages`)、Cloudflare Pagesへは`wrangler pages deploy`の直接アップロード(Git連携ビルドを使わないため「500ビルド/月」制限の対象外。ファイル数2万/1ファイル25MiB制限のみ——公式ドキュメントで確認済み)。
- GitHub Pagesの「毎時10ビルド」soft limitは独自Actionsワークフロー使用時は適用外(公式ドキュメントで確認済み)。公開リポジトリのためActions実行時間は無料。

## 3. 更新機構(N-5: 反映5分以内)

1. **Workers Cron(毎分)**: 高頻度フィードに条件付きGET(`If-Modified-Since`)→ 直近90秒以内の`<updated>`があれば GitHub API `workflow_dispatch` を呼ぶ。ステートレス設計(Workers KVの無料書き込み上限1,000回/日を回避)。CPU消費は数ms(無料枠10ms内)。
2. **Actions schedule(5分毎)**: トリガー欠落・Workers障害時のフォールバック。無条件に生成を実行。
3. **build-deploy.yml**: `concurrency: group=deploy, cancel-in-progress: true` で多重起動を吸収。手順: 長期フィード取得→全電文取得(並列・失敗リトライ)→生成→2系統デプロイ。所要目標90秒以内。
4. **ステートレス再生成**: 前回状態を持たず、毎回「長期フィード(数日分の全入電)」から現在有効な電文集合を再構築する。冪等で、取りこぼし・二重処理の問題が構造的に発生しない。取得量削減のため電文本文はETagベースのActionsキャッシュを併用(任意最適化)。

想定反映時間: 検知(≤60s)+dispatch/キュー(10〜60s)+生成・デプロイ(30〜90s)= **約2〜4分**(要件N-5の5分以内)。

## 4. ページ構成・URL設計

| URL | 内容 | 想定サイズ(gzip後) |
|---|---|---|
| `/` | 全国概況: 警報発表中の府県一覧(特別警報・危険警報・警報の別)、最新地震3件、津波現況、各ページへのリンク | ≤5KB |
| `/p/{官署コード}` | 府県ページ: 当該府県の警報・注意報の詳細(市町村等の発表区域単位)+府県天気予報+週間天気予報 | ≤8KB |
| `/eq` | 地震: 直近の震度速報・震源震度情報 10件 | ≤6KB |
| `/tsunami` | 津波: 警報・注意報・予報の現況(平時は「現在、津波警報・注意報等は発表されていません」) | ≤3KB |
| `/about` | 運営者・非公式明示・免責・出典・限界(圏外には効かない)・更新の仕組み | ≤4KB |

- 府県ページに警報と天気予報を**統合**する(利用者は自分の県のページ1リクエストで用が足りる——低速回線での往復回数最小化)。
- URLは短く(`/p/130000` 等)、トップから2タップ以内で全情報に到達。
- 平時にも意味のあるページ(天気予報)を同居させることで、ブックマーク・ホーム画面追加の平時価値を持たせる(#10: サイト内に到達支援「機能」は入れないが、平時価値はコンテンツで実現する)。

## 5. HTML・CSS設計(N-1〜N-3, #6)

- `<!doctype html>`+`lang="ja"`+`meta viewport`のセマンティックHTML。見出し・定義リスト・最小限のtable。
- CSSはインライン1KB程度: 可読フォントサイズ(相対指定)、警報種別の色分け(色のみに依存しない——名称テキスト併記)、`prefers-color-scheme`対応(数行)。
- JSなし。鮮度はR-1の取得時刻表示で判断可能(将来、0.5KB以下の任意インラインJSで「◯分前」強調を漸進的強化として検討可。無くても情報は欠けない)。
- 文字エンコーディングUTF-8、gzip/brotliはCDN側で自動。
- `_headers`(Cloudflare Pages)で`Cache-Control: max-age=60`程度の短TTL+`ETag`。

## 6. 監視・通知(N-11)

- **monitor.yml(15分毎)**: ①公開中ページの取得時刻が閾値(30分)超なら異常、②フィード`<updated>`の停滞検知、③2系統の死活確認(HTTP 200)。異常時はActionsのfailure(=GitHubからのメール通知)+Issueの自動起票。
- ビルド失敗はActionsの標準通知。
- 劣化警告(R-4)は監視とは独立に、生成時にフィード鮮度から自動判定して埋め込む。

## 7. デプロイ・環境

- 開発中は `*.pages.dev` / `*.github.io` で動作させ、公開時に独自ドメインをCloudflare Pages(主系)に割当て。GitHub Pagesはミラーとして常時同期(aboutページに相互のミラーURLを明記し、片系障害時の代替先を利用者に示す)。
- 秘密情報: Cloudflare APIトークン(Pages deploy用)・GitHub PAT(workflow_dispatch用、fine-grained・最小権限)のみ。リポジトリSecretsで管理。
- ドメイン名は未決(公開前に依頼者が決定。短さ・打ちやすさを推奨基準とする)。

## 8. 「新たな防災気象情報」(2026-05-28)対応 — 電文仕様調査の結果

> 本節は一次情報(気象庁の報道発表・配信資料に関する技術情報)の調査完了後に確定する。(調査進行中)

## 9. 将来拡張との接続(N-13)

- `fetch.py`はソースアダプタ構造(`JmaXmlFeedSource` / 将来`DmdataSource`)。DMDATA導入時はWebSocket受信の常駐プロセスが必要になるため、Linode Nanode(月$5・東京)に`main.py`をsystemd timer/serviceで載せ替える。生成・描画系は無変更。
- Lアラート(避難情報)は2026年12月の総務省新規約公表後に再評価(#1)。掲載する場合も本設計のページ構成に府県ページ内セクションとして追加可能。

## 10. テスト計画(受け入れ基準に対応)

1. **単体**: パーサは実電文(フィードから採取した現物+気象庁サンプル電文)によるゴールデンテスト。新体系の全警報種別コードの表示名変換を網羅。
2. **性能**: 既存の128kbps計測ハーネス(prototype/measure)を流用し、全ページ種別で表示完了2秒以内を確認。
3. **連続運転**: 公開前に1週間以上の自動更新運転を行い、反映遅延の分布・失敗率を計測(受け入れ基準2)。
4. **障害演習**: フィード停滞の模擬(過去時刻の`<updated>`)で劣化警告と監視通知の発火を確認。片系デプロイ失敗時に他系が更新継続することを確認。
