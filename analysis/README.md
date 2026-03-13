# PoliMirror 分析モジュール

## 使用モデル
全ての分析にはAnthropic Claude APIを使用します。
使用モデル・バージョン・判定ロジックは各スクリプト内に明示します。

## 分析スクリプト
- `promise_scorer.py` - 公約達成度スコアリング
- `suspicion_tracker.py` - 疑惑ステータス管理
- `transparency_scorer.py` - 透明性スコア算出

## スコアリング方針
詳細は docs/scoring_policy.md を参照。

## 原則
- 事実と分析は明確に分離する
- 分析結果には必ず使用モデル・バージョンを付記する
- 判定ロジックは全て公開する
- 同一基準で良い面・悪い面の両方を評価する
