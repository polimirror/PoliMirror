"""
PoliMirror - 発言×資金 矛盾検出バッチ実行
v1.0.0

発言データと政治資金データの両方がある全議員に対して
contradiction_detector を実行する。

使用法:
  python batch_contradiction_detector.py              # 全対象
  python batch_contradiction_detector.py --test 10    # テスト（10名）
  python batch_contradiction_detector.py --skip-existing  # 既存スキップ
"""
import json
import os
import sys
import time
import traceback
from datetime import datetime

# 同ディレクトリのモジュールをインポート
sys.path.insert(0, os.path.dirname(__file__))
from contradiction_detector import (
    detect_contradictions,
    save_contradictions,
    load_financial_data,
)

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")), ".env"))

import anthropic

# === 定数 ===
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
SPEECHES_DIR = os.path.join(PROJECT_ROOT, "data", "speeches")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")

API_INTERVAL = 3  # seconds between API calls


def find_eligible_politicians():
    """発言データ＋資金データの両方がある議員を返す"""
    speech_names = set(
        d for d in os.listdir(SPEECHES_DIR)
        if os.path.isdir(os.path.join(SPEECHES_DIR, d))
    )

    eligible = []
    for d in sorted(os.listdir(DONATIONS_DIR)):
        dpath = os.path.join(DONATIONS_DIR, d)
        if not os.path.isdir(dpath):
            continue
        # Check if has financial data (summary.json or *_structured.json)
        has_finance = os.path.exists(os.path.join(dpath, "summary.json"))
        if not has_finance:
            has_finance = any(f.endswith("_structured.json") for f in os.listdir(dpath))
        if not has_finance:
            continue
        # Check if has speech data
        if d not in speech_names:
            continue

        # Count speeches
        sdir = os.path.join(SPEECHES_DIR, d)
        speech_count = 0
        for year in os.listdir(sdir):
            ypath = os.path.join(sdir, year)
            if os.path.isdir(ypath):
                speech_count += len([f for f in os.listdir(ypath) if f.endswith(".json")])

        eligible.append({
            "name": d,
            "speech_count": speech_count,
            "has_contradictions": os.path.exists(os.path.join(dpath, "contradictions.json")),
        })

    return eligible


if __name__ == "__main__":
    # Parse args
    test_count = None
    skip_existing = False
    for arg in sys.argv[1:]:
        if arg.startswith("--test"):
            if "=" in arg:
                test_count = int(arg.split("=")[1])
            elif sys.argv.index(arg) + 1 < len(sys.argv):
                test_count = int(sys.argv[sys.argv.index(arg) + 1])
            else:
                test_count = 10
        if arg == "--skip-existing":
            skip_existing = True

    print("=" * 60)
    print("PoliMirror - 矛盾検出バッチ v1.0.0")
    print("=" * 60)

    # Find eligible politicians
    eligible = find_eligible_politicians()
    print(f"\n対象候補: {len(eligible)}名")
    existing = sum(1 for p in eligible if p["has_contradictions"])
    print(f"既存contradictions.json: {existing}名")

    if skip_existing:
        eligible = [p for p in eligible if not p["has_contradictions"]]
        print(f"新規対象: {len(eligible)}名（既存スキップ）")

    if test_count:
        # テストモード: 発言数が多い順に選ぶ（データが豊富な議員）
        eligible.sort(key=lambda x: x["speech_count"], reverse=True)
        eligible = eligible[:test_count]
        print(f"\nテストモード: {test_count}名")

    print(f"\n処理対象:")
    for p in eligible:
        status = "既存あり" if p["has_contradictions"] else "新規"
        print(f"  {p['name']}: 発言{p['speech_count']}件 ({status})")

    # Execute
    client = anthropic.Anthropic()
    os.makedirs(LOGS_DIR, exist_ok=True)

    results = []
    success = 0
    fail = 0
    skip = 0
    empty = 0
    total_tokens_in = 0
    total_tokens_out = 0

    start_time = datetime.now()

    for i, p in enumerate(eligible, 1):
        name = p["name"]
        print(f"\n--- [{i}/{len(eligible)}] {name} (発言{p['speech_count']}件) ---")

        try:
            contradictions = detect_contradictions(name, client)

            if contradictions is None:
                print(f"  [SKIP] データ不足")
                skip += 1
                results.append({"name": name, "status": "skip", "count": 0})
            elif len(contradictions) == 0:
                print(f"  [EMPTY] 矛盾検出なし")
                save_contradictions(name, [])
                empty += 1
                results.append({"name": name, "status": "empty", "count": 0})
            else:
                print(f"  [OK] {len(contradictions)}件検出")
                save_contradictions(name, contradictions)
                success += 1
                results.append({
                    "name": name,
                    "status": "ok",
                    "count": len(contradictions),
                    "titles": [c.get("title", "") for c in contradictions],
                })
        except Exception as e:
            print(f"  [ERROR] {e}")
            traceback.print_exc()
            fail += 1
            results.append({"name": name, "status": "error", "error": str(e)})

        # Rate limit
        if i < len(eligible):
            time.sleep(API_INTERVAL)

    elapsed = (datetime.now() - start_time).total_seconds()

    # Summary
    print(f"\n{'='*60}")
    print(f"バッチ完了")
    print(f"{'='*60}")
    print(f"  処理: {len(eligible)}名")
    print(f"  成功（矛盾あり）: {success}名")
    print(f"  矛盾なし: {empty}名")
    print(f"  スキップ: {skip}名")
    print(f"  エラー: {fail}名")
    print(f"  所要時間: {elapsed:.0f}秒")

    # Show detected contradictions
    if success > 0:
        print(f"\n  【矛盾検出された議員】")
        for r in results:
            if r["status"] == "ok":
                print(f"    {r['name']}: {r['count']}件")
                for t in r.get("titles", []):
                    print(f"      - {t}")

    # Save batch log
    log_path = os.path.join(LOGS_DIR, "batch_contradiction_log.json")
    log_data = {
        "executed_at": datetime.now().isoformat(),
        "test_mode": test_count is not None,
        "total": len(eligible),
        "success": success,
        "empty": empty,
        "skip": skip,
        "fail": fail,
        "elapsed_seconds": elapsed,
        "results": results,
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    print(f"\n  ログ: {log_path}")
