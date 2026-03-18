"""
PoliMirror - 国会議事録API 発言収集
v1.1.0

国会議事録検索システムAPIから議員の発言を収集し、
data/speeches/{議員名}/{YYYY}/{speechID}.json に保存する。

API: https://kokkai.ndl.go.jp/api/speech
"""
import json
import os
import time
import traceback
from datetime import datetime

import requests


PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPEECHES_DIR = os.path.join(PROJECT_ROOT, "data", "speeches")

API_BASE = "https://kokkai.ndl.go.jp/api/speech"
HEADERS = {"User-Agent": "PoliMirror/1.0 (https://polimirror.jp)"}
MAX_RECORDS_PER_PAGE = 100
REQUEST_INTERVAL = 1  # 秒


class SpeechCollector:
    """国会議事録APIから議員発言を収集するクラス"""

    def __init__(self, output_dir: str = SPEECHES_DIR):
        try:
            self.output_dir = output_dir
            self.session = requests.Session()
            self.session.headers.update(HEADERS)
            print(f"[INFO] SpeechCollector 初期化: 出力先={output_dir}")
        except Exception:
            traceback.print_exc()
            raise

    def _clean_name(self, name: str) -> str:
        """スペースを除去して完全一致検索用の名前にする"""
        return name.replace(" ", "").replace("　", "")

    def _fetch_page(self, name: str, start: int) -> dict:
        """1ページ分の発言データを取得する"""
        try:
            params = {
                "speaker": self._clean_name(name),
                "maximumRecords": MAX_RECORDS_PER_PAGE,
                "startRecord": start,
                "recordPacking": "json",
            }
            resp = self.session.get(API_BASE, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            traceback.print_exc()
            raise

    def _get_total_count(self, name: str) -> int:
        """APIから総件数のみ取得する（1回のAPIコール）"""
        try:
            params = {
                "speaker": self._clean_name(name),
                "maximumRecords": 1,
                "startRecord": 1,
                "recordPacking": "json",
            }
            resp = self.session.get(API_BASE, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json().get("numberOfRecords", 0)
        except Exception:
            traceback.print_exc()
            return 0

    def _get_existing_ids(self, name: str) -> set:
        """既存の発言ファイルからspeechIDセットを取得する"""
        existing = set()
        try:
            clean = self._clean_name(name)
            speaker_dir = os.path.join(self.output_dir, clean)
            if not os.path.isdir(speaker_dir):
                return existing

            for root, _dirs, files in os.walk(speaker_dir):
                for fname in files:
                    if fname.endswith(".json") and "_analysis" not in fname:
                        # ファイル名 = speechID.json
                        speech_id = fname[:-5]  # .json除去
                        existing.add(speech_id)
            return existing
        except Exception:
            traceback.print_exc()
            return existing

    def _build_save_path(self, speaker: str, date_str: str, speech_id: str) -> str:
        """保存パスを組み立てる: data/speeches/{speaker}/{YYYY}/{speechID}.json"""
        try:
            year = date_str[:4] if date_str and len(date_str) >= 4 else "unknown"
            safe_speaker = speaker.replace("/", "_").replace("\\", "_")
            safe_id = speech_id.replace("/", "_").replace("\\", "_")
            return os.path.join(self.output_dir, safe_speaker, year, f"{safe_id}.json")
        except Exception:
            traceback.print_exc()
            raise

    def _save(self, speech_data: dict) -> bool:
        """1発言をJSONファイルとして保存する。既存ファイルはスキップ。"""
        try:
            speaker = speech_data.get("speaker", "unknown")
            date_str = speech_data.get("date", "")
            speech_id = speech_data.get("speechID", "unknown")

            path = self._build_save_path(speaker, date_str, speech_id)

            if os.path.exists(path):
                return False  # スキップ

            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(speech_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            traceback.print_exc()
            return False

    def _extract_record(self, raw: dict) -> dict:
        """APIレスポンスのレコードから保存用データを抽出する"""
        try:
            return {
                "speechID": raw.get("speechID", ""),
                "speaker": raw.get("speaker", ""),
                "speakerYomi": raw.get("speakerYomi", ""),
                "speakerGroup": raw.get("speakerGroup", ""),
                "speakerPosition": raw.get("speakerPosition", ""),
                "nameOfHouse": raw.get("nameOfHouse", ""),
                "nameOfMeeting": raw.get("nameOfMeeting", ""),
                "session": raw.get("session", 0),
                "date": raw.get("date", ""),
                "speech": raw.get("speech", ""),
                "speechURL": raw.get("speechURL", ""),
                "meetingURL": raw.get("meetingURL", ""),
                "pdfURL": raw.get("pdfURL", ""),
                "collected_at": datetime.now().isoformat(),
            }
        except Exception:
            traceback.print_exc()
            raise

    def collect(self, name: str) -> dict:
        """指定議員の全発言を収集する（差分収集対応）"""
        stats = {"total": 0, "saved": 0, "skipped": 0, "failed": 0}
        try:
            # Step1: 総件数だけ確認（1回のAPIコール）
            total_records = self._get_total_count(name)
            stats["total"] = total_records

            if total_records == 0:
                print(f"  [SKIP] {name}: 発言データなし")
                return stats

            # Step2: 既存ファイル数と比較
            existing_ids = self._get_existing_ids(name)
            if len(existing_ids) >= total_records:
                stats["skipped"] = total_records
                print(f"  [SKIP] {name}: {total_records}件 収集済み")
                return stats

            diff = total_records - len(existing_ids)
            print(f"  [COLLECT] {name}: 総数={total_records} 既存={len(existing_ids)} 差分={diff}")

            # Step3: 差分のみ収集（既存IDはメモリ上でスキップ）
            start = 1
            while start <= total_records:
                time.sleep(REQUEST_INTERVAL)
                data = self._fetch_page(name, start)

                records = data.get("speechRecord", [])
                if not records:
                    break

                for rec in records:
                    try:
                        speech_id = rec.get("speechID", "")
                        if speech_id in existing_ids:
                            stats["skipped"] += 1
                            continue

                        extracted = self._extract_record(rec)
                        saved = self._save(extracted)
                        if saved:
                            stats["saved"] += 1
                        else:
                            stats["skipped"] += 1
                    except Exception:
                        traceback.print_exc()
                        stats["failed"] += 1

                fetched_so_far = start + len(records) - 1
                if stats["saved"] > 0 or fetched_so_far % 500 < 100:
                    print(f"    [{fetched_so_far}/{total_records}] 保存={stats['saved']} スキップ={stats['skipped']}")

                start += MAX_RECORDS_PER_PAGE

            print(f"  [DONE] {name}: 保存={stats['saved']} スキップ={stats['skipped']} 失敗={stats['failed']} (総数={stats['total']})")
            return stats

        except Exception:
            traceback.print_exc()
            print(f"  [ERROR] {name}: 収集中にエラー発生")
            return stats

    def collect_batch(self, names: list[str]) -> dict:
        """複数議員の発言を順番に収集する"""
        all_stats = {}
        try:
            print("=" * 60)
            print(f"PoliMirror 国会議事録収集 v1.0.0")
            print(f"対象議員: {len(names)}名")
            print("=" * 60)

            start_time = time.time()

            for i, name in enumerate(names, 1):
                print(f"\n--- [{i}/{len(names)}] {name} ---")
                stats = self.collect(name)
                all_stats[name] = stats

            elapsed = time.time() - start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)

            print("\n" + "=" * 60)
            print("[RESULT] 収集結果サマリー")
            print("=" * 60)
            total_saved = 0
            total_skipped = 0
            total_failed = 0
            for name, st in all_stats.items():
                print(f"  {name}: 総数={st['total']} 保存={st['saved']} スキップ={st['skipped']} 失敗={st['failed']}")
                total_saved += st["saved"]
                total_skipped += st["skipped"]
                total_failed += st["failed"]
            print(f"\n  合計: 保存={total_saved} スキップ={total_skipped} 失敗={total_failed}")
            print(f"  所要時間: {minutes}分{seconds}秒")
            print("=" * 60)

            return all_stats

        except Exception:
            traceback.print_exc()
            return all_stats


def main():
    """テスト実行: 3名の議員で収集テスト"""
    try:
        collector = SpeechCollector()
        test_names = ["安倍晋三", "石破茂", "野田佳彦"]
        collector.collect_batch(test_names)
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    main()
