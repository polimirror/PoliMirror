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

### 記録の原則
- 悪いことも良いことも同じ基準で記録する
- 事実と分析は明確に分離する
- 分析にはClaude APIを使用し使用モデルを明示する

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
- PostgreSQL（構造化データ）
- Elasticsearch（全文検索）
- FastAPI（バックエンドAPI）
- Next.js（SaaSフロントエンド）
- Quartz（静的サイト公開）
- GitHub + Cloudflare Pages（ホスティング）

## 本日の実装済み（2026-03-22）
- 曖昧語分析完了（ambiguous_ranking.json）
- 誠実さスコアウィジェット（SVG五角形・score_widget_generator.py）
- 参議院当選回数修正（sangiin.py v1.1.0）
- OCRパイプライン準備完了（seiji_shikin_ocr.py）
- トップページ改善・UI修正複数

## 重要ルール追加
- 曖昧語率は「使用率（含む発言数÷総発言数）」で計算
  回数ではなく率がメイン指標（公平性のため）
- スコア設計は与党（答弁側）と野党（質問側）の
  構造的差異を常に考慮すること

## つながり可視化（2026-03-30実装）
- company_index.json: 72企業・団体の献金データ
- quartz/content/donations/: 72ページの献金元別ページ
- pipeline/processors/donation_reverse_index.py
- pipeline/processors/donation_page_writer.py
- pipeline/processors/donation_analyzer.py（Claude API構造化解析）
- OCRパイプライン: seiji_shikin_ocr.py（総務省SS20231124対応）
  → 9議員+8政党処理済み
  → 都道府県選管分は未対応（今後の課題）
