# 国会議事録スクレイパー

## 概要
国立国会図書館「国会会議録検索システム」の公式APIを使用して
議員の発言を自動収集しPostgreSQLに保存する。

**注意**: スクレイピングではなくAPIを使用。robots.txtの問題なし。

## API
- 公式ドキュメント: https://kokkai.ndl.go.jp/api.html
- エンドポイント: https://kokkai.ndl.go.jp/api/speech

## セットアップ

```bash
pip install -r requirements.txt
```

`.env` ファイルを作成:
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=polimirror
DB_USER=postgres
DB_PASSWORD=your_password
```

データベース作成:
```bash
psql -U postgres -f schema.sql
```

## 使い方

```bash
# 議員名で収集
python main.py 山田太郎

# 期間指定
python main.py 山田太郎 --from 2020-01-01 --until 2024-12-31

# 全議員収集（要実装）
python main.py --all
```

## ファイル構成
- `config.py` - 設定（環境変数読み込み）
- `api_client.py` - 国会議事録API クライアント
- `parser.py` - APIレスポンス解析
- `db_writer.py` - PostgreSQL書き込み
- `main.py` - メイン実行ファイル
- `schema.sql` - データベーススキーマ
- `logs/` - ログ出力先
