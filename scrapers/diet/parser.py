"""
PoliMirror - APIレスポンス解析
v1.0.0
"""
import traceback
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SpeechRecord:
    """国会発言1件を表すデータクラス"""
    speech_id: str
    issue_id: Optional[str]
    politician_name: str
    politician_name_yomi: Optional[str]
    party: Optional[str]
    position: Optional[str]
    role: Optional[str]
    house: Optional[str]
    meeting_name: Optional[str]
    issue_number: Optional[str]
    session_number: Optional[int]
    date: Optional[str]
    speech_order: Optional[int]
    speech_text: str
    speech_url: Optional[str]
    meeting_url: Optional[str]
    pdf_url: Optional[str]


def parse_speech(raw: dict) -> SpeechRecord:
    """
    APIレスポンスの1件をSpeechRecordに変換する

    APIフィールド対応:
        speechID -> speech_id
        issueID -> issue_id
        speaker -> politician_name
        speakerYomi -> politician_name_yomi
        speakerGroup -> party (所属会派)
        speakerPosition -> position (肩書き)
        speakerRole -> role (証人/参考人/公述人)
        nameOfHouse -> house
        nameOfMeeting -> meeting_name
        issue -> issue_number
        session -> session_number
        date -> date
        speechOrder -> speech_order
        speech -> speech_text
        speechURL -> speech_url
        meetingURL -> meeting_url
        pdfURL -> pdf_url
    """
    try:
        session = raw.get('session')
        if session is not None:
            try:
                session = int(session)
            except (ValueError, TypeError):
                session = None

        speech_order = raw.get('speechOrder')
        if speech_order is not None:
            try:
                speech_order = int(speech_order)
            except (ValueError, TypeError):
                speech_order = None

        return SpeechRecord(
            speech_id=raw.get('speechID', ''),
            issue_id=raw.get('issueID'),
            politician_name=raw.get('speaker', ''),
            politician_name_yomi=raw.get('speakerYomi'),
            party=raw.get('speakerGroup'),
            position=raw.get('speakerPosition'),
            role=raw.get('speakerRole'),
            house=raw.get('nameOfHouse'),
            meeting_name=raw.get('nameOfMeeting'),
            issue_number=raw.get('issue'),
            session_number=session,
            date=raw.get('date'),
            speech_order=speech_order,
            speech_text=raw.get('speech', ''),
            speech_url=raw.get('speechURL'),
            meeting_url=raw.get('meetingURL'),
            pdf_url=raw.get('pdfURL'),
        )
    except Exception:
        traceback.print_exc()
        raise


def parse_speeches(raw_list: list) -> list[SpeechRecord]:
    """複数件を一括変換する。パース失敗した件はスキップしてログ出力"""
    results = []
    errors = 0
    for raw in raw_list:
        try:
            results.append(parse_speech(raw))
        except Exception:
            errors += 1
            traceback.print_exc()
            logger.error(f'パース失敗: speechID={raw.get("speechID", "不明")}')

    if errors:
        logger.warning(f'パース完了: 成功{len(results)}件 失敗{errors}件')
    else:
        logger.info(f'パース完了: {len(results)}件')

    return results
