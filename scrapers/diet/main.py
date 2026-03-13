"""
PoliMirror - 国会議事録収集メインスクリプト
v1.0.0

使い方:
    python main.py 議員名
    python main.py 議員名 --from 2020-01-01 --until 2024-12-31
    python main.py 議員名 --house 衆議院
"""
import argparse
import logging
import os
import sys
import traceback
from datetime import datetime

from api_client import DietAPIClient
from parser import parse_speeches
from db_writer import DBWriter
from config import DEFAULT_START_DATE

# ログ設定
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(
            f'logs/diet_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
            encoding='utf-8',
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def collect_politician(
    name: str,
    start_date: str = None,
    end_date: str = None,
    house: str = None,
) -> tuple[int, int, int]:
    """
    議員1人の発言を全件収集する

    Args:
        name: 議員名
        start_date: 開始日 YYYY-MM-DD
        end_date: 終了日 YYYY-MM-DD
        house: 院名（衆議院/参議院）

    Returns:
        (API取得件数, DB成功件数, DB失敗件数)
    """
    try:
        if not start_date:
            start_date = DEFAULT_START_DATE

        logger.info(f'=== 収集開始: {name} ({start_date}〜{end_date or "現在"}) ===')
        started_at = datetime.now()

        # API取得
        client = DietAPIClient()
        raw_speeches = client.get_all_speeches(
            speaker=name,
            start_date=start_date,
            end_date=end_date,
            name_of_house=house,
        )
        total = len(raw_speeches)
        logger.info(f'{name}: API取得完了 {total}件')

        if total == 0:
            logger.warning(f'{name}: 発言が見つかりませんでした')
            return 0, 0, 0

        # パース
        speeches = parse_speeches(raw_speeches)
        logger.info(f'{name}: パース完了 {len(speeches)}件')

        # DB書き込み
        db = DBWriter()
        try:
            success, error = db.insert_speeches_bulk(speeches)

            finished_at = datetime.now()
            elapsed = (finished_at - started_at).total_seconds()

            # 収集ログをDBに記録
            db.log_collection(
                script_name='diet/main.py',
                started_at=started_at,
                finished_at=finished_at,
                total_count=total,
                success_count=success,
                error_count=error,
            )

            logger.info(
                f'=== 収集完了: {name} ===\n'
                f'  API取得: {total}件\n'
                f'  DB成功: {success}件\n'
                f'  DB失敗: {error}件\n'
                f'  所要時間: {elapsed:.1f}秒'
            )
            return total, success, error

        finally:
            db.close()

    except Exception:
        traceback.print_exc()
        logger.error(f'{name}: 収集中にエラーが発生しました')
        return 0, 0, 0


def main():
    try:
        parser = argparse.ArgumentParser(
            description='PoliMirror 国会議事録収集スクリプト',
        )
        parser.add_argument('name', help='議員名')
        parser.add_argument('--from', dest='start_date', default=None, help='開始日 YYYY-MM-DD')
        parser.add_argument('--until', dest='end_date', default=None, help='終了日 YYYY-MM-DD')
        parser.add_argument('--house', default=None, help='院名（衆議院/参議院）')

        args = parser.parse_args()

        logger.info(f'PoliMirror 国会議事録収集 v1.0.0')
        logger.info(f'対象: {args.name}')

        total, success, error = collect_politician(
            name=args.name,
            start_date=args.start_date,
            end_date=args.end_date,
            house=args.house,
        )

        print(f'\n完了: API取得{total}件 / DB成功{success}件 / DB失敗{error}件')

    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
