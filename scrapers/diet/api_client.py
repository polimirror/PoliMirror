"""
PoliMirror - 国会会議録検索システムAPIクライアント
公式API: https://kokkai.ndl.go.jp/api.html
v1.0.0
"""
import time
import traceback
import logging
import requests
from config import DIET_API_BASE, REQUEST_INTERVAL, MAX_RECORDS, REQUEST_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)


class DietAPIClient:
    """国会会議録検索システムAPIクライアント"""

    def __init__(self):
        try:
            self.base_url = DIET_API_BASE
            self.session = requests.Session()
            self.session.headers.update({'User-Agent': USER_AGENT})
            self.last_request_time = 0
            logger.info(f'APIクライアント初期化完了: {self.base_url}')
        except Exception:
            traceback.print_exc()
            raise

    def _wait_interval(self):
        """リクエスト間隔を守る"""
        elapsed = time.time() - self.last_request_time
        if elapsed < REQUEST_INTERVAL:
            wait = REQUEST_INTERVAL - elapsed
            logger.debug(f'{wait:.1f}秒待機')
            time.sleep(wait)

    def search_speeches(
        self,
        speaker: str = None,
        start_date: str = None,
        end_date: str = None,
        any_word: str = None,
        name_of_house: str = None,
        name_of_meeting: str = None,
        session_from: int = None,
        session_to: int = None,
        start_record: int = 1,
        max_records: int = MAX_RECORDS,
    ) -> dict:
        """
        発言単位の検索を行う

        Args:
            speaker: 発言者名（OR検索）
            start_date: 開会日付始点 YYYY-MM-DD
            end_date: 開会日付終点 YYYY-MM-DD
            any_word: 検索語（AND検索）
            name_of_house: 院名（衆議院/参議院/両院/両院協議会）
            name_of_meeting: 会議名（OR検索）
            session_from: 国会回次始点
            session_to: 国会回次終点
            start_record: 検索結果の開始位置（1〜）
            max_records: 最大取得件数（1〜100）

        Returns:
            APIレスポンスのdict
        """
        try:
            params = {
                'startRecord': start_record,
                'maximumRecords': min(max_records, 100),
                'recordPacking': 'json',
            }

            if speaker:
                params['speaker'] = speaker
            if start_date:
                params['from'] = start_date
            if end_date:
                params['until'] = end_date
            if any_word:
                params['any'] = any_word
            if name_of_house:
                params['nameOfHouse'] = name_of_house
            if name_of_meeting:
                params['nameOfMeeting'] = name_of_meeting
            if session_from is not None:
                params['sessionFrom'] = session_from
            if session_to is not None:
                params['sessionTo'] = session_to

            self._wait_interval()

            response = self.session.get(
                f'{self.base_url}/speech',
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            self.last_request_time = time.time()

            response.raise_for_status()

            data = response.json()
            total = data.get('numberOfRecords', 0)
            returned = data.get('numberOfReturn', 0)
            logger.info(
                f'API応答: 全{total}件中 {start_record}〜{start_record + returned - 1} '
                f'(speaker={speaker}, from={start_date}, until={end_date})'
            )
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f'APIリクエスト失敗: {e}')
            traceback.print_exc()
            raise
        except Exception:
            traceback.print_exc()
            raise

    def get_all_speeches(
        self,
        speaker: str,
        start_date: str = None,
        end_date: str = None,
        name_of_house: str = None,
    ) -> list:
        """
        指定条件の発言を全件取得する（ページング対応）

        Args:
            speaker: 発言者名
            start_date: 開始日 YYYY-MM-DD
            end_date: 終了日 YYYY-MM-DD
            name_of_house: 院名

        Returns:
            speechRecordのリスト
        """
        try:
            from datetime import date as date_cls

            if not end_date:
                end_date = date_cls.today().strftime('%Y-%m-%d')

            all_speeches = []
            start_record = 1

            while True:
                result = self.search_speeches(
                    speaker=speaker,
                    start_date=start_date,
                    end_date=end_date,
                    name_of_house=name_of_house,
                    start_record=start_record,
                )

                speeches = result.get('speechRecord', [])
                if not speeches:
                    logger.info(f'{speaker}: これ以上の発言なし (startRecord={start_record})')
                    break

                all_speeches.extend(speeches)

                total = int(result.get('numberOfRecords', 0))
                next_pos = result.get('nextRecordPosition')

                logger.info(f'{speaker}: {len(all_speeches)}/{total}件取得済み')

                if next_pos is None or int(next_pos) > total:
                    break

                start_record = int(next_pos)

            logger.info(f'{speaker}: 全件取得完了 合計{len(all_speeches)}件')
            return all_speeches

        except Exception:
            traceback.print_exc()
            raise
