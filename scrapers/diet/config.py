"""
PoliMirror - 国会議事録スクレイパー設定
v1.0.0
"""
import os
import traceback
from dotenv import load_dotenv

try:
    load_dotenv()

    # データベース
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'polimirror')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')

    # 国会議事録API
    DIET_API_BASE = 'https://kokkai.ndl.go.jp/api'
    REQUEST_INTERVAL = 5  # 秒（礼儀として5秒空ける）
    MAX_RECORDS = 100     # 1回のAPIコールで取得する最大件数（上限100）
    REQUEST_TIMEOUT = 30  # リクエストタイムアウト秒

    # 収集設定
    TARGET_HOUSES = ['衆議院', '参議院']
    DEFAULT_START_DATE = '2000-01-01'

    # User-Agent
    USER_AGENT = 'PoliMirror/1.0 (政治透明化プロジェクト; https://github.com/ama3net/PoliMirror)'

except Exception:
    traceback.print_exc()
    raise
