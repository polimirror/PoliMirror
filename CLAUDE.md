# PoliMirror - Claude Code指示ファイル

## プロジェクト概要
日本の政治家約35,000人の言動を記録する
政治透明化データベース。

## 絶対に守るルール

### データの原則
- 一次ソースのみ使用する
  （国会議事録・官報・裁判確定記録・議員公式発言）
- 噂・まとめサイト・匿名情報は使わない
- 出典は必ず3重保存
  （元URL・WebArchive URL・S3スクリーンショット）
- 全トランザクションに source_url を必須とする
- MDテーブルには出典列を必ず付ける

### 記録の原則
- 悪いことも良いことも同じ基準で記録する
- 事実と分析は明確に分離する
- 分析にはClaude APIを使用し使用モデルを明示する
- 「判断は読者に委ねる」を必ず明記する

### スクレイピングの原則
- robots.txtを必ず遵守する
- リクエスト間隔は最低5秒
- 深夜帯（0時〜6時）のみ実行
- ログインが必要なページは収集しない

### 信頼度スコア
★★★★★ 国会議事録・官報・裁判確定記録
★★★★☆ 主要報道機関の署名記事
★★★☆☆ 地方紙・業界紙の署名記事
★★☆☆☆ 週刊誌・ネットメディア（実名記者あり）
★☆☆☆☆ 使用しない

### コード品質
- 全スクリプトにエラーハンドリングを入れる
- ログは必ず出力する
- 処理件数・成功件数・失敗件数を記録する

## 技術スタック
- Python（スクレイピング・分析）
- Quartz（静的サイト公開）
- GitHub + Cloudflare Pages（ホスティング）
- Claude API（haiku: OCR構造化解析・注目データ検出・矛盾検出）

## ページ設計原則（2026-04-03確定）
- 注目データは横線（---）で各エントリを分離
- 免責文はObsidian Callout（> [!note]）で本文と区別
- 見出し（###）と本文のサイズ差を明確に
- note風の読み物スタイル・データの羅列にしない
- 絵文字・記号は使わない
- 同トピックの文は1段落にまとめる

## パイプライン一覧

### データ収集
- pipeline/collectors/legislation_collector.py
  → 質問主意書・議員立法（任意の議員名対応）

### データ処理
- pipeline/processors/donation_analyzer.py
  → 旧形式: OCR→サマリー構造化（270件対応済み）
- pipeline/processors/nishida_transaction_extractor.py
  → 新形式: OCR→全トランザクション抽出（source_url付き）
- pipeline/processors/add_source_urls.py
  → 既存transactions.jsonにsource_urlを追加
- pipeline/processors/highlight_detector.py
  → 注目データ自動検出（python highlight_detector.py {議員名}）
- pipeline/processors/contradiction_detector.py
  → 発言×資金の矛盾検出（python contradiction_detector.py {議員名}）
- pipeline/processors/donation_reverse_index.py
  → 企業→議員の逆引きインデックス
- pipeline/processors/donation_page_writer.py
  → 献金元ページ自動生成

## 完成済みリファレンス: 西田昌司
- 全トランザクション287件（4団体×2年・全件source_url付き）
- 注目データ5件（Claude API自動検出）
- 発言×資金の照合3件（Claude API自動検出）
- 国会発言2,297件（全議員6,682名中300位・上位4.5%）
- MDページ: quartz/content/politicians/参議院/自民/西田 昌司.md

## 現在のカバレッジ
- 国会発言: 259万件（全議員）
- 政治資金structured.json: 270件（旧形式）
- 政治資金全トランザクション: 287件（西田昌司のみ・新形式）
- 企業・団体: 507社 / 660エントリ / 507ページ
- 都道府県: 45県対応（高知県非公開・東京都JS動的のみ未対応）

## 重要ルール
- 曖昧語率は「使用率（含む発言数÷総発言数）」で計算
  回数ではなく率がメイン指標（公平性のため）
- スコア設計は与党（答弁側）と野党（質問側）の
  構造的差異を常に考慮すること
- 競合との差別化: 発言259万件×資金データの掛け算
  （political-finance-database.comには発言データがない）
