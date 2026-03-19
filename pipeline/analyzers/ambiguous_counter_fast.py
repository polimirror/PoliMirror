"""
PoliMirror - 曖昧語カウンター（並列処理版） v2.0.0

data/speeches/ 以下の全議員を multiprocessing.Pool(16) で並列処理。
議員ディレクトリ単位で分割し、16プロセスで同時処理する。

出力:
  data/processed/ambiguous_ranking.json
  data/processed/ambiguous_word_total.json
"""
import json
import os
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from multiprocessing import Pool

from tqdm import tqdm

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPEECHES_DIR = os.path.join(PROJECT_ROOT, "data", "speeches")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "processed")

AMBIGUOUS_WORDS = [
    "検討します", "検討いたします", "検討してまいります",
    "努力します", "努力いたします", "努力してまいります",
    "前向きに", "前向きに検討",
    "善処します", "善処いたします",
    "適切に", "適切に対応",
    "しっかりと", "しっかり対応", "しっかり取り組",
    "真摯に", "真摯に受け止め",
    "早急に検討", "早急に対応",
    "慎重に検討", "慎重に対処",
    "十分に検討", "十分に対応",
    "引き続き検討", "引き続き対応",
    "総合的に判断", "総合的に検討",
    "不断の努力", "最善を尽くし",
    "関係省庁と連携", "関係者と協議",
    "国民の理解を得ながら",
]


def process_politician_dir(dir_path):
    """
    議員1名分のディレクトリを処理し、集計結果を返す。
    各ワーカープロセスで実行される。
    """
    result = {
        "name": "", "yomi": "", "party": "", "house": "",
        "total_ambiguous": 0, "speech_count": 0,
        "by_word": {},
        "error_count": 0,
    }
    by_word = defaultdict(int)

    try:
        for root, _dirs, files in os.walk(dir_path):
            for fname in files:
                if not fname.endswith(".json") or "_analysis" in fname:
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    speech_text = data.get("speech", "")
                    if not speech_text:
                        continue

                    # 議員情報（最後に読んだもので上書き＝同一人物なので問題なし）
                    result["name"] = data.get("speaker", "")
                    result["yomi"] = data.get("speakerYomi", "") or data.get("speaker", "unknown")
                    result["party"] = data.get("speakerGroup", "")
                    result["house"] = data.get("nameOfHouse", "")
                    result["speech_count"] += 1

                    # 曖昧語カウント
                    for word in AMBIGUOUS_WORDS:
                        c = speech_text.count(word)
                        if c > 0:
                            by_word[word] += c
                            result["total_ambiguous"] += c

                except Exception:
                    result["error_count"] += 1

    except Exception:
        traceback.print_exc()

    result["by_word"] = dict(by_word)
    return result


if __name__ == "__main__":
    try:
        print("=" * 60)
        print("PoliMirror 曖昧語カウンター（並列16プロセス版） v2.0.0")
        print("=" * 60)

        # 1. 全議員ディレクトリを収集
        print("[1/3] 議員ディレクトリ収集中...")
        all_dirs = sorted([
            os.path.join(SPEECHES_DIR, d)
            for d in os.listdir(SPEECHES_DIR)
            if os.path.isdir(os.path.join(SPEECHES_DIR, d))
        ])
        print(f"  → {len(all_dirs):,} 名分のディレクトリ")

        # 2. 並列処理
        print("[2/3] 並列処理開始（16プロセス）...")
        results = []
        total_errors = 0

        with Pool(processes=16) as pool:
            for r in tqdm(pool.imap(process_politician_dir, all_dirs),
                          total=len(all_dirs), desc="処理中", unit="名"):
                results.append(r)
                total_errors += r.get("error_count", 0)

        print(f"  → 完了: {len(results):,} 名処理, エラー={total_errors}")

        # 3. 集計・出力
        print("[3/3] 集計・出力中...")

        # yomiでグループ化（同名別人対策）
        grouped = defaultdict(lambda: {
            "name": "", "yomi": "", "party": "", "house": "",
            "total_ambiguous": 0, "speech_count": 0,
            "by_word": defaultdict(int),
        })

        word_totals = defaultdict(int)
        total_speeches = 0

        for r in results:
            if r["speech_count"] == 0:
                continue
            yomi = r["yomi"]
            g = grouped[yomi]
            g["name"] = r["name"]
            g["yomi"] = r["yomi"]
            g["party"] = r["party"]
            g["house"] = r["house"]
            g["total_ambiguous"] += r["total_ambiguous"]
            g["speech_count"] += r["speech_count"]
            total_speeches += r["speech_count"]

            for word, cnt in r["by_word"].items():
                g["by_word"][word] += cnt
                word_totals[word] += cnt

        # ランキング生成
        ranking = []
        for yomi, pol in grouped.items():
            by_word_sorted = dict(sorted(pol["by_word"].items(), key=lambda x: x[1], reverse=True))
            top_word = next(iter(by_word_sorted), "")
            ambiguous_rate = round(pol["total_ambiguous"] / pol["speech_count"], 3) if pol["speech_count"] > 0 else 0.0
            ranking.append({
                "name": pol["name"], "yomi": pol["yomi"],
                "party": pol["party"], "house": pol["house"],
                "total_ambiguous": pol["total_ambiguous"],
                "speech_count": pol["speech_count"],
                "ambiguous_rate": ambiguous_rate,
                "by_word": by_word_sorted, "top_word": top_word,
            })

        ranking.sort(key=lambda x: x["total_ambiguous"], reverse=True)
        word_totals_sorted = dict(sorted(word_totals.items(), key=lambda x: x[1], reverse=True))

        # ファイル出力
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        ranking_path = os.path.join(OUTPUT_DIR, "ambiguous_ranking.json")
        with open(ranking_path, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_speeches": total_speeches,
                "politicians": ranking,
            }, f, ensure_ascii=False, indent=2)
        print(f"  → {ranking_path}")

        word_total_path = os.path.join(OUTPUT_DIR, "ambiguous_word_total.json")
        with open(word_total_path, "w", encoding="utf-8") as f:
            json.dump(word_totals_sorted, f, ensure_ascii=False, indent=2)
        print(f"  → {word_total_path}")

        # 結果表示
        detected = len([r for r in ranking if r["total_ambiguous"] > 0])
        print("\n" + "=" * 60)
        print(f"[DONE] 総発言数: {total_speeches:,} / エラー: {total_errors}")
        print(f"       曖昧語検出議員数: {detected:,}")
        print("=" * 60)

        print("\n■ 曖昧語 使用回数 TOP20 議員")
        print("-" * 60)
        for i, r in enumerate(ranking[:20], 1):
            print(f"  {i:2d}. {r['name']}（{r['party']}・{r['house']}）")
            print(f"      曖昧語={r['total_ambiguous']:,}回 / 発言={r['speech_count']:,}件 / rate={r['ambiguous_rate']:.3f} / 最多=「{r['top_word']}」")

        print("\n■ 曖昧語別 出現回数 TOP10")
        print("-" * 60)
        for i, (word, cnt) in enumerate(list(word_totals_sorted.items())[:10], 1):
            print(f"  {i:2d}. 「{word}」: {cnt:,}回")

        print("=" * 60)

    except Exception:
        traceback.print_exc()
