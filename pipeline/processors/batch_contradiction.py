"""
PoliMirror - 矛盾検出バッチ実行
v1.1.0

トランザクション抽出済み（summary.json保有）かつ発言データありの
議員に対して contradiction_detector.py をバッチ実行する。

使用法:
  python batch_contradiction.py              # 全議員実行
  python batch_contradiction.py --test 10    # 10名テスト
  python batch_contradiction.py --resume     # 未処理のみ再開
  python batch_contradiction.py --tx-only    # トランザクション抽出済みのみ（デフォルト）
"""
import json
import os
import sys
import time
import traceback
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")), ".env"))

import anthropic

from contradiction_detector import detect_contradictions, save_contradictions

# === 定数 ===
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
SPEECHES_DIR = os.path.join(PROJECT_ROOT, "data", "speeches")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "data", "batch_results")
RESULT_PATH = os.path.join(RESULTS_DIR, "contradiction_batch.json")


def find_target_politicians(resume=False, tx_only=True):
    """トランザクション抽出済み+発言データありの議員リストを返す

    Args:
        resume: True=既存contradictions.jsonがある議員をスキップ
        tx_only: True=summary.json(トランザクション抽出済み)保有者のみ対象
    """
    try:
        # 資金データ保有議員
        donation_politicians = set()
        for name in os.listdir(DONATIONS_DIR):
            full = os.path.join(DONATIONS_DIR, name)
            if not os.path.isdir(full):
                continue
            if tx_only:
                # summary.json = トランザクション抽出済みの新形式
                if not os.path.exists(os.path.join(full, "summary.json")):
                    continue
                # トランザクション件数が0のみの議員は除外
                has_tx = False
                for f in os.listdir(full):
                    if f.endswith("_transactions.json"):
                        with open(os.path.join(full, f), encoding="utf-8") as fh:
                            d = json.load(fh)
                            if d.get("transaction_count", 0) > 0:
                                has_tx = True
                                break
                if not has_tx:
                    continue
            donation_politicians.add(name)

        # 発言データ保有議員
        speech_dirs = set()
        for name in os.listdir(SPEECHES_DIR):
            full = os.path.join(SPEECHES_DIR, name)
            if os.path.isdir(full):
                speech_dirs.add(name)

        targets = sorted(donation_politicians & speech_dirs)

        if resume:
            already_done = set()
            for name in targets:
                cpath = os.path.join(DONATIONS_DIR, name, "contradictions.json")
                if os.path.exists(cpath):
                    already_done.add(name)
            print(f"  処理済みスキップ: {len(already_done)}名")
            targets = [t for t in targets if t not in already_done]

        return targets
    except Exception:
        traceback.print_exc()
        return []


def run_batch(limit=None, resume=False):
    """バッチ矛盾検出を実行する"""
    start_time = time.time()
    os.makedirs(RESULTS_DIR, exist_ok=True)

    targets = find_target_politicians(resume=resume, tx_only=True)
    total = len(targets)

    if limit:
        targets = targets[:limit]

    print("=" * 60)
    print(f"PoliMirror - 矛盾検出バッチ v1.0.0")
    print(f"対象議員: {len(targets)}名 (全候補: {total}名)")
    print(f"モード: {'テスト' if limit else '全件'}{' (resume)' if resume else ''}")
    print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    client = anthropic.Anthropic()

    results = {
        "started_at": datetime.now().isoformat(),
        "mode": f"test_{limit}" if limit else "full",
        "total_targets": len(targets),
        "completed": 0,
        "skipped": 0,
        "found": 0,
        "errors": 0,
        "details": [],
    }

    for i, name in enumerate(targets):
        idx = f"[{i+1}/{len(targets)}]"
        print(f"\n{idx} {name}")

        detail = {"politician": name, "status": None, "count": 0, "error": None}

        try:
            contradictions = detect_contradictions(name, client)

            if contradictions is None:
                print(f"  -> スキップ（データ不足）")
                detail["status"] = "skipped"
                results["skipped"] += 1
            elif len(contradictions) == 0:
                print(f"  -> 矛盾なし")
                save_contradictions(name, [])
                detail["status"] = "no_contradiction"
                results["completed"] += 1
            else:
                print(f"  -> {len(contradictions)}件検出!")
                save_contradictions(name, contradictions)
                detail["status"] = "found"
                detail["count"] = len(contradictions)
                detail["titles"] = [c.get("title", "") for c in contradictions]
                results["completed"] += 1
                results["found"] += 1

        except Exception as e:
            traceback.print_exc()
            detail["status"] = "error"
            detail["error"] = str(e)
            results["errors"] += 1

        results["details"].append(detail)

        # 中間保存（5件ごと）
        if (i + 1) % 5 == 0:
            results["last_saved"] = datetime.now().isoformat()
            with open(RESULT_PATH, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

        # API rate limit対策: 1件ごとに2秒待機
        if i < len(targets) - 1:
            time.sleep(2)

    # 最終保存
    elapsed = time.time() - start_time
    results["finished_at"] = datetime.now().isoformat()
    results["elapsed_seconds"] = round(elapsed, 1)

    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # サマリー表示
    print("\n" + "=" * 60)
    print("バッチ完了サマリー")
    print("=" * 60)
    print(f"  対象: {len(targets)}名")
    print(f"  完了: {results['completed']}名")
    print(f"  スキップ: {results['skipped']}名")
    print(f"  矛盾検出: {results['found']}名")
    print(f"  エラー: {results['errors']}名")
    print(f"  所要時間: {elapsed:.0f}秒")
    print(f"  結果: {RESULT_PATH}")

    # 矛盾検出された議員を表示
    found_details = [d for d in results["details"] if d["status"] == "found"]
    if found_details:
        print(f"\n矛盾検出された議員:")
        for d in found_details:
            print(f"  {d['politician']}: {d['count']}件")
            for t in d.get("titles", []):
                print(f"    - {t}")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="矛盾検出バッチ実行")
    parser.add_argument("--test", type=int, default=None, help="テスト実行（件数指定）")
    parser.add_argument("--resume", action="store_true", help="未処理のみ再開")
    args = parser.parse_args()

    run_batch(limit=args.test, resume=args.resume)
