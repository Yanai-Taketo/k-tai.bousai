# 公開セットアップ手順(依頼者向け)

設計書§2〜§3・§7の「Pagesのみ」構成を稼働させるための手順。コードはすべてリポジトリにあり、
以下のアカウント設定のみ依頼者の作業が必要です(所要30分程度・費用ゼロ)。

## 0. 前提

- 更新パイプラインの`schedule`(5分毎cron・15分毎監視)は**既定ブランチのワークフローだけが動く**
  というGitHubの仕様のため、開発ブランチを既定ブランチ(main)へマージした後に有効になります。
- ローカル・手動での生成はいつでも可能: `python3 -m generator.main`(標準ライブラリのみ、site/に出力)。
  テストは `python3 -m unittest discover -s tests`。

## 1. GitHub Pages(ミラー系)

1. リポジトリの Settings → Pages → Build and deployment → Source を **GitHub Actions** にする。
2. 以後、build-deployワークフローが実行されるたびに `https://<ユーザー名>.github.io/k-tai.bousai/` へ配信される。

## 2. Cloudflare Pages(主系)

> **なぜ「Git連携(既存のGitリポジトリをインポート)」ではなくDirect Uploadなのか**:
> Git連携のビルドは無料プランで**月500回まで**の制限がある(Cloudflare公式 Pages Limits)。
> 本サイトは5分毎+フィード更新検知でデプロイするため月8,000回超となり、約2日で枠を使い切って
> 以後Cloudflare側の更新が止まる。`wrangler`によるDirect Uploadはビルドシステムを通らないため
> この制限の対象外。また、Git連携は生成HTMLを毎回リポジトリへコミットする構成になり、
> 履歴の肥大化とActionsへの書き込み権限付与(現在はread only)という別の問題も生む。
> APIトークンは下記の通り最小権限(Pages Editのみ)で作成し、漏えい時の影響を限定する。

1. Cloudflareアカウントを作成(無料プラン)。
2. ダッシュボード → Workers & Pages → Create → **Pages** → **Direct Upload** でプロジェクトを作成
   (プロジェクト名例: `k-tai-bousai`。初回は空のダミーファイルのアップロードで良い)。
3. **Account ID** を控える(ダッシュボード右側に表示)。
4. My Profile → API Tokens → Create Token → 「Custom token」で権限
   **Account / Cloudflare Pages / Edit** のみのトークンを作成。
5. GitHubリポジトリの Settings → Secrets and variables → Actions に設定:
   - Secret `CLOUDFLARE_API_TOKEN` = 上記トークン
   - Secret `CLOUDFLARE_ACCOUNT_ID` = Account ID
   - Variable `CF_PAGES_PROJECT` = プロジェクト名(例: `k-tai-bousai`)

## 3. 毎分トリガー(Cloudflare Worker)

1. GitHubで **fine-grained PAT** を作成: 対象リポジトリ=本リポジトリのみ、
   Repository permissions → **Actions: Read and write**。有効期限は運用に合わせて設定
   (失効するとトリガーが止まり、5分毎cronのフォールバックだけになる。失効前に更新する)。
2. 手元(またはCloud Shell等)で:
   ```
   cd worker
   npx wrangler@4 login
   npx wrangler@4 deploy
   npx wrangler@4 secret put GITHUB_TOKEN   # ← 上記PATを入力
   ```
3. `wrangler.toml` の `GITHUB_REPO` / `GITHUB_BRANCH` が実際の値と一致しているか確認。

## 4. 監視の通知先

1. リポジトリの Variable `SITE_URLS` に公開URLをカンマ区切りで設定
   (例: `https://k-tai-bousai.pages.dev,https://<ユーザー名>.github.io/k-tai.bousai`)。
2. 監視異常はワークフロー失敗(GitHubからのメール)+ラベル`monitor`付きIssueで通知される。
   GitHubの通知メールが受信できることを確認しておく。

## 5. 独自ドメイン(公開時)

1. ドメインを取得し、Cloudflare Pagesプロジェクトの Custom domains に追加(Cloudflareがドメインの
   DNSを管理する構成が最も簡単)。
2. GitHub Pages側はミラーとしてそのまま残し、aboutページに相互のURLを記載する(片系障害時の代替先)。

## 6. 公開前チェックリスト(要件定義書§5の受け入れ基準)

- [ ] 1週間以上の連続自動運転で反映遅延・失敗率を確認(status.jsonとActionsログ)
- [ ] フィード停滞を模擬した監視通知テスト
- [ ] 実機・実回線(速度制限SIM等)での表示確認
- [ ] 警報表示名と気象庁ページの突合(新体系)
- [ ] 依頼者による文言・免責の最終確認
