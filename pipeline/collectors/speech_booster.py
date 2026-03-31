"""
PoliMirror - 献金議員の発言データ拡充
v1.0.0

献金データがある議員のうち発言データが不足している議員に対して
国会議事録APIから発言を取得する。
"""
import json
import os
import time
import traceback
from datetime import datetime

import requests

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPEECHES_DIR = os.path.join(PROJECT_ROOT, "data", "speeches")
GAP_LIST_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "speech_gap_list.json")
DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")

API_URL = "https://kokkai.ndl.go.jp/api/speech"
MAX_RECORDS = 100
REQUEST_INTERVAL = 1


def get_existing_ids(politician_name):
    """既存のspeechIDセットを取得"""
    safe = politician_name
    speech_dir = os.path.join(SPEECHES_DIR, safe)
    ids = set()
    if not os.path.isdir(speech_dir):
        return ids
    for year_dir in os.listdir(speech_dir):
        yp = os.path.join(speech_dir, year_dir)
        if not os.path.isdir(yp):
            continue
        for f in os.listdir(yp):
            if f.endswith(".json"):
                ids.add(f.replace(".json", ""))
    return ids


def fetch_speeches(name, max_records=MAX_RECORDS):
    """国会議事録APIから発言を取得"""
    speeches = []
    start = 1
    while start <= max_records:
        try:
            time.sleep(REQUEST_INTERVAL)
            params = {
                "speaker": name,
                "maximumRecords": min(100, max_records - start + 1),
                "startRecord": start,
                "recordPacking": "json",
            }
            r = requests.get(API_URL, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()

            records = data.get("speechRecord", [])
            if not records:
                break

            for rec in records:
                speeches.append({
                    "speechID": rec.get("speechID", ""),
                    "speaker": rec.get("speaker", ""),
                    "speakerYomi": rec.get("speakerYomi", ""),
                    "speakerGroup": rec.get("speakerGroup", ""),
                    "speakerPosition": rec.get("speakerPosition"),
                    "nameOfHouse": rec.get("nameOfHouse", ""),
                    "nameOfMeeting": rec.get("nameOfMeeting", ""),
                    "session": rec.get("session", ""),
                    "date": rec.get("date", ""),
                    "speech": rec.get("speech", ""),
                    "speechURL": rec.get("speechURL", ""),
                    "meetingURL": rec.get("meetingURL", ""),
                    "pdfURL": rec.get("pdfURL", ""),
                    "collected_at": datetime.now().isoformat(),
                })

            start += len(records)
            if len(records) < 100:
                break
        except Exception:
            traceback.print_exc()
            break

    return speeches


def save_speech(politician_name, speech):
    """1件の発言をファイルに保存"""
    safe = politician_name
    date = speech.get("date", "")
    year = date[:4] if date else "unknown"
    speech_id = speech.get("speechID", "unknown")

    out_dir = os.path.join(SPEECHES_DIR, safe, year)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{speech_id}.json")

    if os.path.exists(out_path):
        return False  # 重複

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(speech, f, ensure_ascii=False, indent=2)
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("PoliMirror - 献金議員 発言データ拡充 v1.0.0")
    print("=" * 60)

    # 献金データあり議員一覧
    target_pols = []
    for d in sorted(os.listdir(DONATIONS_DIR)):
        dp = os.path.join(DONATIONS_DIR, d)
        if not os.path.isdir(dp):
            continue
        structs = [f for f in os.listdir(dp) if f.endswith("_structured.json")]
        if not structs:
            continue
        for s in structs:
            with open(os.path.join(dp, s), "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("type") == "politician":
                target_pols.append(d)
                break

    # 発言件数でソート（少ない順に優先処理）
    speech_counts = {}
    for pol in target_pols:
        sd = os.path.join(SPEECHES_DIR, pol)
        count = 0
        if os.path.isdir(sd):
            for year in os.listdir(sd):
                yp = os.path.join(sd, year)
                if os.path.isdir(yp):
                    count += len([f for f in os.listdir(yp) if f.endswith(".json")])
        speech_counts[pol] = count

    # 100件未満の議員を対象
    targets = [(pol, cnt) for pol, cnt in sorted(speech_counts.items(), key=lambda x: x[1]) if cnt < 100]

    print(f"\n献金データあり議員: {len(target_pols)}名")
    print(f"発言100件未満: {len(targets)}名（対象）")

    stats = {"success": 0, "new_speeches": 0, "api_zero": 0, "error": 0}

    for i, (pol, current_cnt) in enumerate(targets, 1):
        need = MAX_RECORDS - current_cnt
        if need <= 0:
            continue

        print(f"\n[{i}/{len(targets)}] {pol}: 現在{current_cnt}件 → {MAX_RECORDS}件目標")

        existing_ids = get_existing_ids(pol)
        speeches = fetch_speeches(pol, max_records=MAX_RECORDS)

        if not speeches:
            print(f"  API: 0件")
            stats["api_zero"] += 1
            continue

        new_count = 0
        for speech in speeches:
            sid = speech.get("speechID", "")
            if sid not in existing_ids:
                if save_speech(pol, speech):
                    new_count += 1

        print(f"  API: {len(speeches)}件取得, 新規{new_count}件保存")
        stats["success"] += 1
        stats["new_speeches"] += new_count

        if i % 10 == 0:
            print(f"\n--- 進捗: {i}/{len(targets)}名 ---")
            print(f"  成功: {stats['success']}, 新規発言: {stats['new_speeches']}")
            print()

    print(f"\n{'='*60}")
    print("完了")
    print(f"{'='*60}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
