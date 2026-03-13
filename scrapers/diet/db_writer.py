"""
PoliMirror - PostgreSQL書き込み
v1.0.0
"""
import traceback
import logging
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
from parser import SpeechRecord

logger = logging.getLogger(__name__)


class DBWriter:
    """PostgreSQLへの書き込みを管理するクラス"""

    def __init__(self):
        try:
            self.conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
            )
            self.conn.autocommit = False
            logger.info(f'DB接続成功: {DB_HOST}:{DB_PORT}/{DB_NAME}')
        except Exception:
            traceback.print_exc()
            raise

    def insert_speech(self, speech: SpeechRecord) -> bool:
        """
        発言を1件挿入する（speech_idで重複排除）
        """
        sql = """
            INSERT INTO statements (
                speech_id, issue_id,
                politician_name, politician_name_yomi,
                party, position, role, house, meeting_name,
                issue_number, session_number, date,
                speech_order, speech_text, speech_url,
                meeting_url, pdf_url,
                source_reliability
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, 5
            )
            ON CONFLICT (speech_id) DO NOTHING
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, (
                    speech.speech_id,
                    speech.issue_id,
                    speech.politician_name,
                    speech.politician_name_yomi,
                    speech.party,
                    speech.position,
                    speech.role,
                    speech.house,
                    speech.meeting_name,
                    speech.issue_number,
                    speech.session_number,
                    speech.date,
                    speech.speech_order,
                    speech.speech_text,
                    speech.speech_url,
                    speech.meeting_url,
                    speech.pdf_url,
                ))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            traceback.print_exc()
            logger.error(f'DB書き込み失敗: speech_id={speech.speech_id}')
            return False

    def insert_speeches_bulk(self, speeches: list[SpeechRecord]) -> tuple[int, int]:
        """
        複数件を一括挿入する

        Returns:
            (成功件数, 失敗件数)
        """
        try:
            success = 0
            error = 0
            for speech in speeches:
                if self.insert_speech(speech):
                    success += 1
                else:
                    error += 1

            logger.info(f'一括挿入完了: 成功{success}件 失敗{error}件')
            return success, error

        except Exception:
            traceback.print_exc()
            raise

    def log_collection(
        self,
        script_name: str,
        started_at: datetime,
        finished_at: datetime,
        total_count: int,
        success_count: int,
        error_count: int,
        error_details: str = None,
    ):
        """収集ログをDBに記録する"""
        sql = """
            INSERT INTO collection_logs (
                script_name, started_at, finished_at,
                total_count, success_count, error_count,
                error_details
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, (
                    script_name, started_at, finished_at,
                    total_count, success_count, error_count,
                    error_details,
                ))
            self.conn.commit()
            logger.info('収集ログをDBに記録しました')
        except Exception:
            self.conn.rollback()
            traceback.print_exc()
            logger.error('収集ログのDB記録に失敗')

    def close(self):
        """接続を閉じる"""
        try:
            self.conn.close()
            logger.info('DB接続を閉じました')
        except Exception:
            traceback.print_exc()
