# ドメイン選定 — 決定と根拠

- 作成日: 2026-08-15
- 位置づけ: 独自ドメインの選定調査。**依頼者の決定は `bosai.ne.jp`**(決定#25)。本書はその根拠と、登録・運用に必要な確認事項を残す。
- 関連要件: N-12(費用)、N-8/N-9(可用性)、N-15(国が作成したかのような態様にしない)、R-5(非公式である旨の明示)

> **注意(公開リポジトリのため)**: 本書は取得可能な候補ドメイン名を含む。
> **`bosai.ne.jp` を登録してから**本書を `main` に取り込むこと。

## 1. 決定

**`bosai.ne.jp`**(依頼者決定)。2026-08-15 の JPRS WHOIS 照会で未登録を確認[^whois]。

属性型JPドメイン名(`ne.jp` = 日本国内のネットワークサービス提供者向け)。
将来の防災サービス展開を第1階層サブドメインで受けられる**傘ドメイン**として機能する(§3)。

| 役割 | ホスト | ドメイン |
|---|---|---|
| 旗艦(現サイト) | Cloudflare Pages | `bosai.ne.jp`(apex)+ `www.bosai.ne.jp` |
| 主系(素のURL) | Cloudflare Pages | `k-tai-bousai.pages.dev` — **そのまま残す**(既定で残る[^cfpages-redirect]) |
| 副系 | GitHub Pages | `yanai-taketo.github.io/k-tai.bousai` — **カスタムドメインを設定しない** |
| 将来サービス | Cloudflare Pages(別プロジェクト) | `<service>.bosai.ne.jp`(第1階層まで) |

副系にカスタムドメインを設定してはならない理由は §6.1(実測)。

### 1.1 検討時に挙げた懸念と、その扱い

本書の初版では `bosai.ne.jp` を見送り案としていた。理由は、`bosai` が
`bosai.go.jp`(国立研究開発法人防災科学技術研究所)と同一ラベルであり、
N-15「国が作成したかのような態様にならない」に触れうる点である。

依頼者の決定を受けて採用する。判断の整理は以下のとおり。

- `.ne.jp` は「日本国内のネットワークサービス提供者」を示す属性型ラベルであり、
  `.go.jp`(政府機関)とは登録資格が明確に異なる。**同一ラベルなのは第3レベルのみ**である。
- ただし一般の利用者が属性ラベルを読み分ける保証はない。誤認防止は**サイト側の表示で担保する**。
  現行実装で既に満たしている:
  - 全ページのヘッダ「気象庁発表の軽量ミラー(個人運営)」(`render.py`)
  - about「本サイトは気象庁の公式サイトではなく、個人が運営しています」(R-5)
- 追加の推奨: WHOISに公開される**ネットワークサービス名**(§2.3)を、個人運営と分かる名称にする。

## 2. `.ne.jp` 固有の要件(登録前に確定させること)

汎用JP(`example.jp`)とは登録資格・WHOIS・費用がいずれも異なる。

### 2.1 登録資格 — 個人でも登録できる

JPRS直営(JPDirect)の記載[^jpdirect]:

- 対象: 「日本国内のネットワークサービス提供者が、**不特定または多数の利用者に対して営利または非営利で提供するネットワークサービス**」
- 提供者要件: 「ネットワークサービス提供者は、**日本に在住する個人**または日本国法に基づいて設立された法人であること」
- 「利用者に対して提供する**ネットワークサービスの内容が明文化されている**こと」
- 提出書類: 「原則不要(登録後、登録資格が確認できない場合は書類提出が必要)」
- 本数: 「1サービスごとに一つのドメイン名を登録できる(同一組織でもサービスごとに異なるNE.JPを登録できる)」[^jprs-spec]

**本件の適合**: 不特定多数へ無償で提供するWebサービスであり、内容は about ページと本リポジトリの
要件定義書で明文化されている。資格を満たす。ただし**登録時の資格確認はJPRS側の判断**であり、
レジストラによっては書類提出を求められる(さくらのドメインは申請書・証明書類を案内している[^sakura])。
**書類要件の軽いレジストラを選ぶこと**。

### 2.2 WHOIS — 汎用JPより開示が多い(重要)

| 項目 | 汎用JP(`example.jp`) | 属性型JP(`example.ne.jp`) |
|---|---|---|
| 登録者名フィールド | あり | **なし**(代わりに「ネットワークサービス名」) |
| 登録者情報非表示設定 | **使える**(2014-08-18〜)[^jprs-conceal] | **使えない**(対象は汎用JP・都道府県型JPのみ) |
| 担当者情報 | 公開連絡窓口(代理公開可) | 登録担当者・技術連絡担当者のJPハンドルが公開され、**担当者情報検索で氏名・電子メイル・組織名・電話番号が引ける** |

実測(`iij.ne.jp` の登録担当者ハンドル `TM003JP` を JPRS WHOIS の担当者情報検索で照会、2026-08-15):

```
a. [JPNICハンドル]  TM003JP
b. [氏名]           三膳 孝通
d. [電子メイル]     apply@iij.ad.jp
f. [組織名]         株式会社 インターネットイニシアティブ
o. [電話番号]       03-5205-6500
```

**含意**: 個人で `ne.jp` を登録すると、**氏名・連絡先がWHOISから辿れる**。
汎用JPで使えた「登録者名の非表示」は `ne.jp` では使えない。
申込前に、**レジストラが担当者情報の代理公開に対応するかを確認すること**。
対応しない場合は、公開されて構わない連絡先(専用のメールアドレス等)を用意する。

### 2.3 ネットワークサービス名を決める必要がある

JPRSの規定により、**ネットワークサービス名に個人名は登録できない**[^sakura]。
WHOISに `[ネットワークサービス名]` として公開されるため、サイトの性格が分かる名称にする。
§1.1 の誤認防止の観点から、個人運営であることが読み取れる名称を推奨する。

### 2.4 費用 — 汎用JPの約2倍

| 項目 | 新規 | 更新(年額) | 出典 |
|---|---|---|---|
| `.ne.jp`(さくらのドメイン) | 11,000円 | **7,700円** | [^sakura-price] |
| 参考: 汎用JP(さくらのドメイン) | 3,982円 | 3,982円 | [^sakura-price] |
| 参考: 汎用JP(バリュードメイン) | 2,035円 | 3,889円 | [^vd] |
| 参考: `co.jp`/`or.jp`(バリュードメイン) | 5,177円 | 5,177円 | [^vd] |

いずれも税込。更新7,700円は**月換算約642円**で、N-12「月額実費は数百円以内」の**上限側**に収まる。
`.ne.jp` は取扱レジストラが限られる(バリュードメインは `co.jp`/`or.jp` は扱うが `ne.jp` の掲載がない)ため、
価格差はレジストラ間で大きい。契約前に複数社の**更新料**で比較すること。

## 3. サブドメインによる将来展開

`bosai.ne.jp` を傘とし、サービスごとに第1階層サブドメインを充てる。

| 階層 | 例 | 内容 |
|---|---|---|
| apex | `bosai.ne.jp` | 現在の軽量サイト(旗艦)。主力なのでURLを最短に保つ |
| 第1階層 | `<service>.bosai.ne.jp` | 将来の防災サービス(例: 火山情報、河川など) |

技術的な確認事項:

- **ゾーンとして登録できる**: `ne.jp` は Public Suffix List に収載されている(2026-08-15 実測、`public_suffix_list.dat` に `ne.jp` の行あり)。したがって Cloudflare は `bosai.ne.jp` をゾーンapexとして扱える。
- **サブドメインは第1階層まで**: Cloudflare の Universal SSL はゾーンapexと第1階層サブドメインのみを無料でカバーする[^cfssl]。`ktai.bosai.ne.jp` は対象、`a.b.bosai.ne.jp` は対象外(Total TLS または Advanced Certificate Manager が必要)。
- **サービスごとに別リポジトリ・別Pagesプロジェクト**にする。片方の不具合が他へ伝播しない。Freeプランはアカウントあたり100プロジェクト、プロジェクトあたり100カスタムドメイン[^cfpages-limits]。
- **サービスごとに `github.io` の副系を残す**(§6.1 の結論をサービス単位で適用)。
- `ne.jp` は「1サービスごとに1ドメイン」なので、別サービス用に別の `ne.jp` を取ることも可能だが、
  サブドメインで足りる限り**ドメインは1本に集約する**(費用が本数分、更新失念のリスクも本数分になる)。

**要確認(サービスを増やす前に)**: Cloudflare Pages Freeの「500ビルド/月」はCloudflareのビルドシステムを
使う場合の数字で、現構成(GitHub Actions から `wrangler pages deploy` による Direct Upload)に
適用されるかは公式ドキュメントに明記がない[^cfpages-limits]。数分間隔で更新するサービスを増やす前に実測で確認する。

## 4. 選定基準(要件からの導出)

| # | 基準 | 根拠 | `bosai.ne.jp` の適合 |
|---|---|---|---|
| C1 | 公的機関と誤認されない | N-15, R-5 | △ 第3レベルが `bosai.go.jp` と同一。属性ラベルで区別されるが、サイト側の表示で担保する(§1.1) |
| C2 | 短く、打ち間違えない | 決定#2 | ◎ 11文字。ハイフン・数字なし。`bosai` の綴りは一意に決まる |
| C3 | サービスの性格が伝わる | 決定#6, #9 | ◎ 「防災」そのもの |
| C4 | 到達性の読めるTLD | N-8 | ◎ `.jp` 系 |
| C5 | 単一ベンダに寄せない | N-8/N-9 | ◎ Cloudflare Registrar は JP系を扱わない[^cfreg]ため、レジストラが必然的にCloudflare外になる |
| C6 | 引き継ぎ可能な中立名 | README | ◎ 個人名・地域名・端末名を含まない。将来の展開も縛らない |
| C7 | 月数百円以内 | N-12 | ○ 月約642円。上限側 |

ドメイン名の長さがページ転送量に与える影響は数十バイト規模で、N-1(gzip後10KB以下)に対して無意味である。
**短さは「打ちやすさ・伝えやすさ」の基準であって、軽量性の基準ではない**。

## 5. 空き調査(参考)

### 5.1 方法

- `.jp` 系: JPRS WHOIS(`https://whois.jprs.jp/`)。応答に `該当するデータがありません` を含むものを未登録と判定。
- `.com`/`.net`/`.org`: レジストリ RDAP(Verisign / Public Interest Registry)。HTTP 404 を未登録と判定。
- 実施日: 2026-08-15。照会は延べ約530件。

### 5.2 素の一般名詞は汎用JPでは取れない

| ドメイン | 状態 | 登録者(WHOIS表示) |
|---|---|---|
| `bosai.jp` | 登録済 | 国立研究開発法人防災科学技術研究所 |
| `bousai.jp` | 登録済 | 防災技術センター株式会社 |
| `bousai.ne.jp` | 登録済 | — |
| `bosai.or.jp` / `bousai.or.jp` | 登録済 | — |
| `keiho.jp` / `keihou.jp` | 登録済 | 民間法人・個人 |

**`bosai.ne.jp` は、素の「防災」を第3レベルに使える唯一の空き**であった。これが決定の実質的な決め手になる。

### 5.3 検討したが採用しなかった候補

いずれも2026-08-15時点で未登録。将来の参考として残す。

| 方向 | 候補 |
|---|---|
| 端末を冠する | `ktai-bousai` `ktaibousai` `ktai-bosai` `k-tai-bousai` `keitai-bousai` `ktai` |
| 説明型 | `mojibosai`(文字防災) `sugubosai` `imabosai` `bosaidayori` `karuibosai` `textbosai` |
| 「〜だけ」型 | `mojidake`(文字だけ) `yomudake`(読むだけ) |
| 軽さの和語 | `karugaru`(軽々) `temijika`(手短) `karusa` `karui` |
| 見張り台の比喩 | `monomi`(物見) `hinomiyagura`(火の見櫓) `hinomidai` `hinoban` `noroshidai` |
| 傘ブランド | `karui-bousai` `open-bousai` `bousai-tools` `keiryo-bousai` `bousaidou` |
| 短い象徴 | `2kb` `hayame` |

却下理由の要点:

- `*.go.jp`: 登録資格が政府機関等に限られ、取得不可。
- `bousai-lite`: 「防災ライト = 防災用の懐中電灯」と読まれる(商品カテゴリとして実在)。
- `machi-bousai`: 自治体サイトに見えるため C1 に反する。
- `ktai-*`: 決定#2「4Gケータイ対応は主目標としない」と名前が逆のシグナルになり、将来の展開も端末名で縛る。
- `2kb`: 実測で地震詳細ページが既に2,454Bあり、名前が事実とずれる。
- 新gTLD(`.site` `.online` 等): 受信側フィルタ・社内プロキシでの扱いが読みにくい(**実測ではなく判断**)。

## 6. 運用上の発見(構成に直結する)

### 6.1 GitHub Pages にカスタムドメインを設定すると、素のURLが消える(実測)

カスタムドメインを設定したプロジェクトサイトの `<user>.github.io/<repo>` は、301でカスタムドメインへ転送される。
2026-08-15 に実在サイトで確認した。

```
$ curl -sSI https://jekyll.github.io/jekyll/
HTTP/2 301 ... location: http://jekyllrb.com/

$ curl -sSI https://chartjs.github.io/Chart.js/
HTTP/2 301 ... location: http://www.chartjs.org/Chart.js/
```

**含意**: 副系(GitHub Pages)にカスタムドメインを設定すると、`yanai-taketo.github.io/k-tai.bousai` は
「独自ドメインへのリダイレクタ」に変わる。独自ドメインのDNSが引けない状態では、副系も道連れで開けなくなる。
**「片方が落ちても、もう片方が生きている」という現行の設計(N-8)が壊れる**。したがって副系には設定しない。

### 6.2 Cloudflare Pages の apex を使うと、DNS が Cloudflare に集約される

Cloudflare Pages で apex(`bosai.ne.jp`)をカスタムドメインにする場合、
**ネームサーバをCloudflareに向けることが必須**である(サブドメインなら外部DNSでCNAMEを向けるだけでよい)[^cfpages-custom]。

**含意**: 独自ドメインを apex で使う限り、DNSはCloudflareに置くことになる。
つまり Cloudflare の広域障害時には、独自ドメイン配下は全サービスが名前解決から落ちる。
これは §6.1 の結論(副系は独自ドメインの外に置く)を補強する。**独自ドメインを介さない生存経路を必ず1本残す**。

### 6.3 `*.pages.dev` はカスタムドメイン設定後も既定で残る

Cloudflare Pages は自動リダイレクトをしない。ドメイン不要の経路を潰したい場合のみ、自分でBulk Redirectsを設定する[^cfpages-redirect]。
本件では**潰さない**(生存経路として残す)。

### 6.4 分散状況(決定後の構成)

| 層 | 主系 | 副系 |
|---|---|---|
| レジストラ | 国内レジストラ(`ne.jp` 取扱社) | (副系はドメインを使わない) |
| DNS | Cloudflare | GitHub(`github.io`) |
| ホスティング | Cloudflare Pages | GitHub Pages |
| 生成・デプロイ | GitHub Actions(共通) | 同左 |

独自ドメイン導入後も、**ドメイン・DNSに一切依存しない経路(`yanai-taketo.github.io/k-tai.bousai`)が残る**。
ただしその経路は、ドメインが引けない状況では利用者に案内する手段がない(aboutページも読めない)。
周知は依頼者のブログ等、サイト外で行う必要がある(決定#10と整合)。

### 6.5 コード変更は不要

`generator/` に自ホストの絶対URL・`<link rel=canonical>` は存在しない(内部リンクはすべて相対/ルート相対)。
外部絶対URLは気象庁とGitHubリポジトリのみ。**ドメイン導入で生成コードの変更は生じない**。
変更が要るのは以下だけ。

- `tools/monitor.py` が読む環境変数 `SITE_URLS` に `https://bosai.ne.jp` を追加(監視対象を増やす)。
- aboutページに「予備の配信先」を1行追加することを推奨(現在は記載がなく、README にしかない)。数十バイト。

## 7. 登録・設定の手順

1. **レジストラを選ぶ**。判断軸は ①`ne.jp` を扱うか ②更新料 ③登録時の提出書類の重さ ④担当者情報の代理公開に対応するか(§2.2)。
2. **ネットワークサービス名を決める**(§2.3)。個人名は不可。WHOISに公開される。
3. `bosai.ne.jp` を登録。**自動更新ON**、レジストラのアカウントに2要素認証。
4. Cloudflare にゾーン `bosai.ne.jp` を追加し、レジストラ側のネームサーバをCloudflareのものへ変更(apex利用のため必須、§6.2)。
5. Cloudflare Pages のプロジェクトにカスタムドメイン `bosai.ne.jp` と `www.bosai.ne.jp` を追加(ダッシュボード経由。DNSレコードの手動追加のみでは522になる[^cfpages-custom])。
6. DNSSEC を有効化。
7. **GitHub Pages にはカスタムドメインを設定しない**(§6.1)。
8. `SITE_URLS` に新ドメインを追加。旧URL(`k-tai-bousai.pages.dev`)は監視対象に残す。
9. README の「公開中」と about ページの案内を更新。副系URLを about に1行明記する。
10. `pages.dev` からのリダイレクトは**設定しない**(生存経路として残す、§6.3)。

---

[^whois]: JPRS WHOIS(一次)。https://whois.jprs.jp/ 2026-08-15に候補全件を照会。未登録判定は応答文字列「該当するデータがありません」。担当者情報は検索タイプ `POC` で照会。gTLDはレジストリRDAP(https://rdap.verisign.com/com/v1/ 、https://rdap.verisign.com/net/v1/ 、https://rdap.publicinterestregistry.org/rdap/ )のHTTP 404で判定。
[^jprs-spec]: JPRS「JPドメイン名の種類」(一次)。https://jprs.jp/about/jp-dom/spec/ 全種別に「日本国内に住所をもつ個人・団体・組織」の要件。`ne.jp` は「1サービスごとに一つのドメイン名を登録できます(同一組織でもサービスごとに異なるNE.JPドメイン名を登録できます)」。`co.jp`/`or.jp` は原則1組織1ドメインで、`or.jp` は法人等に限られ個人は登録不可。
[^jpdirect]: JPDirect(JPRS直営)「NE.JPドメイン名の登録」(一次)。https://jpdirect.jp/domain/register/nejp/ 登録資格・提供者要件(日本に在住する個人を含む)・サービス内容の明文化・書類は原則不要。
[^sakura]: さくらのサポート情報「.ne.jpドメイン名登録申請(個人)をしたい(属性型JP)」(一次)。https://help.sakura.ad.jp/domain/2290/ 個人名義での登録が可能であること、およびネットワークサービス名に個人名を登録できない旨。
[^sakura-price]: さくらのドメイン 価格一覧(一次)。https://domain.sakura.ad.jp/specification/ 2026-08-15時点で `.ne.jp` 新規11,000円/更新7,700円、汎用JP 3,982円(いずれも税込)。同社は2026年5月に料金改定を実施している。
[^jprs-conceal]: JPRS「Whois登録者情報非表示設定」(一次)。https://jprs.jp/about/dom-rule/whois-concealment/ **対象は汎用JPドメイン名・都道府県型JPドメイン名**。属性型JP(`ne.jp` 等)は対象外。
[^cfreg]: Cloudflare Registrar(一次)。https://www.cloudflare.com/products/registrar/ 対応TLD一覧 https://www.cloudflare.com/tld-policies/ に `.jp` は含まれない(2026-08-15確認)。
[^cfpages-custom]: Cloudflare Pages「Custom domains」(一次)。https://developers.cloudflare.com/pages/configuration/custom-domains/ apexドメインではネームサーバをCloudflareに向ける必要がある。サブドメインは外部DNSでCNAME可。ダッシュボードで関連付けずにCNAMEだけ追加すると522になる。
[^cfpages-redirect]: Cloudflare Pages「Redirect to custom domain」(一次)。https://developers.cloudflare.com/pages/how-to/redirect-to-custom-domain/ `<project>.pages.dev` は既定で提供され続け、止めたい場合はBulk Redirectsを自分で設定する。
[^cfpages-limits]: Cloudflare Pages「Limits」(一次)。https://developers.cloudflare.com/pages/platform/limits/ Freeプランはアカウントあたり100プロジェクト、プロジェクトあたり100カスタムドメイン、ビルド500回/月。Direct Uploadがビルド上限に含まれるかは明記なし。
[^cfssl]: Cloudflare「Universal SSL」(一次)。https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/ フルセットアップではルートドメインと第1階層サブドメインのみをカバー。より深い階層は Total TLS または Advanced Certificate Manager が必要。
[^vd]: バリュードメイン 料金一覧(一次)。https://www.value-domain.com/domain/price/ 2026-08-15時点で汎用JP 新規2,035円/更新3,889円、`co.jp`/`or.jp` 5,177円(税込)。`ne.jp` の掲載はない。
