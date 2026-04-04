# PoliMirror 引き継ぎドキュメント

> セッション間の文脈を保持するためのファイル。
> 新しいセッション開始時にこのファイルを読み込むこと。

---

## 1. プロジェクト概要

日本の政治家約35,000人の言動を記録する政治透明化データベース。
一次ソースのみ使用。事実と分析を明確に分離。

---

## 2. 技術スタック

- Python（スクレイピング・分析）
- Quartz（静的サイト公開）
- GitHub + Cloudflare Pages（ホスティング）
- Claude API（haiku: OCR構造化解析・注目データ検出・矛盾検出）

---

## 3. ディレクトリ構造

```
PoliMirror/
├── data/
│   ├── speeches/         # 国会発言（議員名/年/会議ID.json）
│   ├── donations/        # 政治資金（議員名/transactions.json, summary.json等）
│   └── legislation/      # 議員立法・質問主意書
├── pipeline/
│   ├── processors/       # データ処理スクリプト
│   │   ├── donation_analyzer.py           # 既存の構造化解析（旧形式）
│   │   ├── nishida_transaction_extractor.py # 全トランザクション抽出（新形式・西田昌司で実証）
│   │   ├── highlight_detector.py          # 注目データ自動検出
│   │   └── contradiction_detector.py      # 発言×資金の矛盾検出
│   └── collectors/
│       └── legislation_collector.py       # 質問主意書収集
├── quartz/
│   ├── content/politicians/  # 議員MDページ
│   └── quartz/quartz/styles/custom.scss  # カスタムCSS
├── polimirror_ideas.md       # アイデアログ
├── polimirror_handover.md    # このファイル
└── CLAUDE.md                 # プロジェクトルール
```

---

## 4. 現在完成していること

✅ 国会発言データ収集（全議員・259万件）
   → data/speeches/ に格納
   → 国会議事録API経由で自動収集済み

✅ 政治資金 旧形式（270件 structured.json）
   → Claude API (haiku) でOCRテキストを構造化
   → 企業・団体・パーティー別に分類
   → 507企業・団体 / 660エントリ / 507ページ

✅ 政治資金全トランザクション抽出（西田昌司で実証）
   → 4団体×2年=287件・競合と同等の粒度
   → pipeline/processors/nishida_transaction_extractor.py

✅ 注目データ自動検出（highlight_detector.py）
   → Claude APIが収支報告書から異常値を自動判定
   → severity: high/medium/low で分類
   → python highlight_detector.py {議員名} で任意の議員に使用可

✅ 発言×資金の矛盾検出（contradiction_detector.py）
   → 国会発言と収支報告書をClaude APIで照合
   → python contradiction_detector.py {議員名} で任意の議員に使用可

✅ 議員ページのデザイン改善
   → custom.scssで見出しサイズ・太さ・区切り線を整備
   → 注目データをnote風の読み物スタイルで表示
   → 横線（---）でエントリを分離

✅ 競合分析完了
   → political-finance-database.com（西田尚史氏）が最大競合
   → 財務トランザクションの粒度は同等になった
   → PoliMirrorの唯一の差別化：発言×資金の掛け算

✅ 政治資金データのカバレッジ
   → 507企業・団体 / 660エントリ / 507ページ
   → 45県対応（高知県非公開・東京都JS動的のみ未対応）
   → 総カバレッジ約31.7%（712名中約227名）

✅ 議員活動実績（西田昌司で実証）
   → 発言数ランキング（全6,682名中の順位算出）
   → 質問主意書検索（全54回次スクレイピング）
   → legislation_collector.py で任意の議員に使用可

✅ Quartzサイト構築
   → 議員ページ・献金元ページ・トップページ
   → TOC・検索・グラフビュー動作
   → Cloudflare Pages連携

---

## 5. 西田昌司ページ（完成済みリファレンス）

ファイル: quartz/content/politicians/参議院/自民/西田 昌司.md

構成:
1. 注目データ（5件・Claude API自動検出）
2. 発言と資金の照合（3件・Claude API自動検出）
3. 基本情報
4. 議員活動実績（発言2,297件・上位4.5%）
5. 国会発言（年別件数・最新発言引用）
6. 政治資金 2023年（収入構成・企業寄付16社・パーティー・出典PDF付き）
7. 政治資金 2022年（同上）
8. 年度推移表
9. 関連政治団体一覧

全セクションに出典URL付き（国会議事録・京都府選管PDF直リンク）。

---

## 6. 主要データファイル（西田昌司）

- data/donations/西田昌司/2022_transactions.json (106件)
- data/donations/西田昌司/2023_transactions.json (181件)
- data/donations/西田昌司/summary.json
- data/donations/西田昌司/highlights.json
- data/donations/西田昌司/contradictions.json
- data/legislation/西田昌司/questions.json (0件)
- data/legislation/西田昌司/activity_summary.json

---

## 7. PDF取得状況

京都府選管から以下の8PDFを取得済み:
- 西田会（2022, 2023）
- 一粒会（2022, 2023）
- 京都医療政策フォーラム（2022, 2023）
- 自由民主党京都府参議院選挙区第四支部（2022, 2023）

未取得:
- 西田昌司後援会（インデックス未登録・存在不明）

---

## 8. カスタムCSS（custom.scss）

```scss
// TOC視認性改善
ul.toc-content.overflow > li > a { opacity: 0.7; &.in-view { opacity: 1; } }

// 見出しサイズ
h1 { font-size: 2em; font-weight: 700; }
h2 { font-size: 1.5em; border-bottom: 2px solid #1a4fa0; }
h3 { font-size: 1.3em !important; font-weight: 700 !important; }
h4 { font-size: 1.1em !important; color: #1a4fa0 !important; }

// blockquote（免責文）
blockquote { background: #f5f7fa !important; border-left: 4px solid #1a4fa0 !important; }
```

---

## 9. 既知の課題

- 東京都53名: JS動的ページでSelenium/Playwright必要
- 高知県: 非公開
- 議員立法: 提出者確認に個別経過ページ参照が必要（未実装）
- OCR日付: 「R5/8/16」形式が残っている（正規化未実装）
- summary1の名寄せ: 「寄附」「寄附金」等の統一が必要

---

## 10. 競合との役割分担（2026-04-04確定）

**「概要はPoliMirror、詳細は競合へ」**

- PoliMirror: 総務省集計表から概要数値（総収入・構成比）を取得
- 競合（political-finance-database.com）: トランザクション明細・検索
- 議員ページから競合に明示的リンク
- 全議員OCRは非現実的 → 集計値＋発言で攻める

### バッチ矛盾検出テスト結果（2026-04-04）
- 10名テスト: 矛盾検出0名
- 原因: 旧形式structured.jsonは企業2-3社・総額のみで粒度不足
- 西田昌司（全トランザクション287件）でのみ成功
- → プロンプト改善より、データソース変更が正解

---

## 11. 次にやること

① 総務省集計Excelから全712名の概要数値取得（最重要）
   → 総収入・総支出・企業献金額・パーティー収入額・構成比
   → 議員名との名寄せ検証
   → これが全議員ページの資金セクションの基盤になる

② 概要数値×発言での矛盾検出プロンプト再設計
   → 全トランザクションなしでも検出できるプロンプトに
   → 「企業献金1,200万円（25%）」レベルで十分検出可能か検証

③ 全議員ページに資金概要＋競合リンクを追加
   → 議員ページテンプレートの確定
   → MDページ自動生成パイプライン

④ X投稿（データが全議員分揃ってから）
   → 「献金×発言の掛け算はここだけ」を軸に

⑤ 政治家アキネーター（データが揃ったら）

---

*最終更新: 2026-04-04*
*書記: Claude*
