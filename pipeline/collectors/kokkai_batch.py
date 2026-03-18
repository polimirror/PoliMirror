"""
PoliMirror - 国会議事録 全議員一括収集
v1.0.0

現職712名の発言を一括で収集し、
収集サマリーを data/processed/speech_summary.json に保存する。
"""
import glob
import json
import os
import time
import traceback
from datetime import datetime

# プロジェクトルート
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

# kokkai.pyからSpeechCollectorをインポート
import sys
sys.path.insert(0, PROJECT_ROOT)
from pipeline.collectors.kokkai import SpeechCollector


DATA_DIR = os.path.join(PROJECT_ROOT, "data", "raw")
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "processed")
SUMMARY_PATH = os.path.join(PROCESSED_DIR, "speech_summary.json")


def find_latest_json(pattern: str) -> str | None:
    """globパターンにマッチする最新のJSONファイルを返す"""
    try:
        files = sorted(glob.glob(pattern))
        if not files:
            return None
        return files[-1]
    except Exception:
        traceback.print_exc()
        return None


def load_member_names(filepath: str) -> list[str]:
    """JSONファイルから議員名リストを取得する"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        names = []
        for m in data.get("members", []):
            name = m.get("name_ja", "")
            if name:
                names.append(name)
        return names
    except Exception:
        traceback.print_exc()
        return []


def main():
    """全議員の発言を一括収集する"""
    try:
        print("=" * 60)
        print("PoliMirror 国会議事録 全議員一括収集 v1.0.0")
        print("=" * 60)

        # 議員名リスト構築
        all_names = []

        shugiin_file = find_latest_json(os.path.join(DATA_DIR, "shugiin_members_*.json"))
        if shugiin_file:
            names = load_member_names(shugiin_file)
            print(f"[INFO] 衆議院: {len(names)}名 ({shugiin_file})")
            all_names.extend(names)
        else:
            print("[WARN] 衆議院データが見つかりません")

        sangiin_file = find_latest_json(os.path.join(DATA_DIR, "sangiin_members_*.json"))
        if sangiin_file:
            names = load_member_names(sangiin_file)
            print(f"[INFO] 参議院: {len(names)}名 ({sangiin_file})")
            all_names.extend(names)
        else:
            print("[WARN] 参議院データが見つかりません")

        # 重複除去（衆参で同名はまずないが念のため）
        unique_names = list(dict.fromkeys(all_names))
        print(f"[INFO] 総対象: {len(unique_names)}名 (重複除去後)")
        print()

        # 収集実行
        collector = SpeechCollector()
        start_time = time.time()
        all_stats = {}
        total = len(unique_names)

        for i, name in enumerate(unique_names, 1):
            print(f"\n{'='*40}")
            print(f"{name} ({i}/{total})")
            print(f"{'='*40}")
            try:
                stats = collector.collect(name)
                all_stats[name] = stats
            except Exception:
                traceback.print_exc()
                all_stats[name] = {"total": 0, "saved": 0, "skipped": 0, "failed": 0, "error": True}

        elapsed = time.time() - start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)

        # サマリー集計
        total_saved = 0
        total_skipped = 0
        total_failed = 0
        zero_count = 0
        collected_count = 0

        for name, st in all_stats.items():
            total_saved += st.get("saved", 0)
            total_skipped += st.get("skipped", 0)
            total_failed += st.get("failed", 0)
            if st.get("total", 0) > 0:
                collected_count += 1
            else:
                zero_count += 1

        # サマリー保存
        os.makedirs(PROCESSED_DIR, exist_ok=True)
        summary = {
            "collected_at": datetime.now().isoformat(),
            "total_politicians": total,
            "collected_politicians": collected_count,
            "zero_speech_politicians": zero_count,
            "total_speeches_saved": total_saved,
            "total_speeches_skipped": total_skipped,
            "total_speeches_failed": total_failed,
            "elapsed_seconds": int(elapsed),
            "per_politician": {
                name: {
                    "total": st.get("total", 0),
                    "saved": st.get("saved", 0),
                    "skipped": st.get("skipped", 0),
                    "failed": st.get("failed", 0),
                }
                for name, st in all_stats.items()
            },
        }

        with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        print("\n" + "=" * 60)
        print("[RESULT] 全議員一括収集 完了")
        print("=" * 60)
        print(f"  対象議員数: {total}名")
        print(f"  発言あり: {collected_count}名")
        print(f"  発言0件: {zero_count}名")
        print(f"  総保存件数: {total_saved}")
        print(f"  スキップ: {total_skipped}")
        print(f"  失敗: {total_failed}")
        print(f"  所要時間: {hours}時間{minutes}分{seconds}秒")
        print(f"  サマリー保存先: {SUMMARY_PATH}")
        print("=" * 60)

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    main()
