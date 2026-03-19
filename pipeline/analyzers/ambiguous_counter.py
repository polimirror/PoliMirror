"""
PoliMirror - 曖昧語カウンター v1.0.0

data/speeches/ 以下の全JSONファイルを読み込み、
各発言(speech)から曖昧語を検出・集計する。

出力:
  data/processed/ambiguous_ranking.json   - 議員別曖昧語ランキング
  data/processed/ambiguous_word_total.json - 語ごとの総出現数
"""
import json
import os
import traceback
from collections import defaultdict
from datetime import datetime, timezone

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


def collect_json_paths():
    """data/speeches/ 以下の全JSONファイルパスを収集"""
    paths = []
    try:
        for root, _dirs, files in os.walk(SPEECHES_DIR):
            for fname in files:
                if fname.endswith(".json") and "_analysis" not in fname:
                    paths.append(os.path.join(root, fname))
    except Exception:
        traceback.print_exc()
    return paths


def count_ambiguous(speech_text):
    """発言テキストから曖昧語の出現回数を返す"""
    counts = {}
    try:
        for word in AMBIGUOUS_WORDS:
            c = speech_text.count(word)
            if c > 0:
                counts[word] = c
    except Exception:
        traceback.print_exc()
    return counts


def run():
    """メイン処理"""
    try:
        print("=" * 60)
        print("PoliMirror 曖昧語カウンター v1.0.0")
        print("=" * 60)

        # 1. JSONファイル収集
        print("[1/4] JSONファイル収集中...")
        json_paths = collect_json_paths()
        total_files = len(json_paths)
        print(f"  → {total_files:,} 件のJSONファイルを検出")

        if total_files == 0:
            print("[ERROR] JSONファイルが見つかりません")
            return

        # 2. 全ファイルを読み込み・集計
        print("[2/4] 曖昧語カウント中...")

        # 議員別集計: key = speakerYomi
        politicians = defaultdict(lambda: {
            "name": "",
            "yomi": "",
            "party": "",
            "house": "",
            "total_ambiguous": 0,
            "speech_count": 0,
            "by_word": defaultdict(int),
        })
        word_totals = defaultdict(int)
        total_speeches = 0
        error_count = 0

        for i, fpath in enumerate(tqdm(json_paths, desc="処理中", unit="件")):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                speech_text = data.get("speech", "")
                if not speech_text:
                    continue

                yomi = data.get("speakerYomi", "") or data.get("speaker", "unknown")
                name = data.get("speaker", "")
                party = data.get("speakerGroup", "")
                house = data.get("nameOfHouse", "")

                total_speeches += 1
                pol = politicians[yomi]
                pol["name"] = name
                pol["yomi"] = yomi
                pol["party"] = party
                pol["house"] = house
                pol["speech_count"] += 1

                counts = count_ambiguous(speech_text)
                for word, c in counts.items():
                    pol["by_word"][word] += c
                    pol["total_ambiguous"] += c
                    word_totals[word] += c

            except Exception:
                error_count += 1
                if error_count <= 5:
                    traceback.print_exc()

            if (i + 1) % 100000 == 0:
                print(f"  [中間] {i + 1:,}/{total_files:,} 処理済み, エラー={error_count}")

        print(f"  → 完了: {total_speeches:,} 発言処理, エラー={error_count}")

        # 3. ランキング生成
        print("[3/4] ランキング生成中...")

        ranking = []
        for yomi, pol in politicians.items():
            try:
                by_word = dict(sorted(pol["by_word"].items(), key=lambda x: x[1], reverse=True))
                top_word = next(iter(by_word), "")
                ambiguous_rate = round(pol["total_ambiguous"] / pol["speech_count"], 3) if pol["speech_count"] > 0 else 0.0

                ranking.append({
                    "name": pol["name"],
                    "yomi": pol["yomi"],
                    "party": pol["party"],
                    "house": pol["house"],
                    "total_ambiguous": pol["total_ambiguous"],
                    "speech_count": pol["speech_count"],
                    "ambiguous_rate": ambiguous_rate,
                    "by_word": by_word,
                    "top_word": top_word,
                })
            except Exception:
                traceback.print_exc()

        ranking.sort(key=lambda x: x["total_ambiguous"], reverse=True)

        word_totals_sorted = dict(sorted(word_totals.items(), key=lambda x: x[1], reverse=True))

        # 4. 出力
        print("[4/4] ファイル出力中...")
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        ranking_output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_speeches": total_speeches,
            "politicians": ranking,
        }

        ranking_path = os.path.join(OUTPUT_DIR, "ambiguous_ranking.json")
        with open(ranking_path, "w", encoding="utf-8") as f:
            json.dump(ranking_output, f, ensure_ascii=False, indent=2)
        print(f"  → {ranking_path}")

        word_total_path = os.path.join(OUTPUT_DIR, "ambiguous_word_total.json")
        with open(word_total_path, "w", encoding="utf-8") as f:
            json.dump(word_totals_sorted, f, ensure_ascii=False, indent=2)
        print(f"  → {word_total_path}")

        # 結果表示
        print("\n" + "=" * 60)
        print(f"[DONE] 総発言数: {total_speeches:,} / エラー: {error_count}")
        print(f"       曖昧語検出議員数: {len([r for r in ranking if r['total_ambiguous'] > 0]):,}")
        print("=" * 60)

        print("\n■ 曖昧語 使用回数 TOP10 議員")
        print("-" * 60)
        for i, r in enumerate(ranking[:10], 1):
            print(f"  {i:2d}. {r['name']}（{r['party']}・{r['house']}）")
            print(f"      曖昧語={r['total_ambiguous']:,}回 / 発言={r['speech_count']:,}件 / rate={r['ambiguous_rate']:.3f} / 最多=「{r['top_word']}」")

        print("\n■ 曖昧語別 出現回数 TOP10")
        print("-" * 60)
        for i, (word, cnt) in enumerate(list(word_totals_sorted.items())[:10], 1):
            print(f"  {i:2d}. 「{word}」: {cnt:,}回")

        print("=" * 60)

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    run()
