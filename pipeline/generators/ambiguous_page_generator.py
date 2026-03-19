"""
PoliMirror - 曖昧語ランキングページ生成 v1.0.0

data/processed/ambiguous_ranking.json と ambiguous_word_total.json を読み込み、
quartz/content/rankings/曖昧語ランキング.md を生成する。
"""
import json
import os
import traceback

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
RANKING_JSON = os.path.join(PROJECT_ROOT, "data", "processed", "ambiguous_ranking.json")
WORD_TOTAL_JSON = os.path.join(PROJECT_ROOT, "data", "processed", "ambiguous_word_total.json")
OUTPUT_MD = os.path.join(PROJECT_ROOT, "quartz", "content", "rankings", "曖昧語ランキング.md")


def find_politician_link(name, party, house):
    """議員名から[[リンク]]パスを検索"""
    try:
        politicians_dir = os.path.join(PROJECT_ROOT, "quartz", "content", "politicians")
        for root, _dirs, files in os.walk(politicians_dir):
            for fname in files:
                if fname.endswith(".md") and fname.replace(".md", "") == name:
                    rel = os.path.relpath(os.path.join(root, fname), os.path.join(PROJECT_ROOT, "quartz", "content"))
                    rel = rel.replace("\\", "/").replace(".md", "")
                    return f"[[{rel}|{name}]]"
    except Exception:
        traceback.print_exc()
    return name


def run():
    """メイン処理"""
    try:
        print("=" * 60)
        print("曖昧語ランキングページ生成 v1.0.0")
        print("=" * 60)

        # データ読み込み
        print("[1/3] データ読み込み中...")
        with open(RANKING_JSON, "r", encoding="utf-8") as f:
            ranking_data = json.load(f)
        with open(WORD_TOTAL_JSON, "r", encoding="utf-8") as f:
            word_totals = json.load(f)

        politicians = ranking_data["politicians"]
        total_speeches = ranking_data["total_speeches"]
        detected_count = len([p for p in politicians if p["total_ambiguous"] > 0])

        print(f"  → 総発言数: {total_speeches:,}, 検出議員: {detected_count:,}名")

        # リンク解決
        print("[2/3] 議員リンク解決中...")
        link_cache = {}
        for p in politicians[:50]:
            key = p["name"]
            if key not in link_cache:
                link_cache[key] = find_politician_link(p["name"], p["party"], p["house"])

        # MD生成
        print("[3/3] Markdown生成中...")

        lines = []
        lines.append('---')
        lines.append('title: "曖昧語ランキング｜国会議員が最も使う言葉"')
        lines.append('description: "「しっかりと」「前向きに」「真摯に」──国会議員が使う曖昧語を国会議事録259万件から集計したランキング"')
        lines.append('tags: ["ランキング", "曖昧語", "データ分析"]')
        lines.append('---')
        lines.append('')
        lines.append('# 国会議員「曖昧語」使用ランキング')
        lines.append('')
        lines.append(f'> 国会議事録{total_speeches:,}件（2026年3月集計）から「しっかりと」「前向きに」「真摯に」等の曖昧語を集計した。')
        lines.append('')
        lines.append('## 曖昧語とは')
        lines.append('国会答弁でよく使われる、具体的な行動・数値・期限を含まない表現。')
        lines.append('「検討します」「前向きに」「しっかりと対応」等。')
        lines.append('')

        # 語別ランキング TOP10
        lines.append('## 曖昧語 種類別ランキング TOP10')
        lines.append('')
        lines.append('| 順位 | 曖昧語 | 国会での総使用回数 |')
        lines.append('|---:|---|---:|')
        for i, (word, cnt) in enumerate(list(word_totals.items())[:10], 1):
            lines.append(f'| {i} | {word} | {cnt:,}回 |')
        lines.append('')

        # 議員別 TOP20
        lines.append('## 議員別 曖昧語使用回数 TOP20')
        lines.append('')
        lines.append('| 順位 | 議員名 | 政党 | 院 | 使用回数 | 発言数 | 使用率 | 最多使用語 |')
        lines.append('|---:|---|---|---|---:|---:|---:|---|')
        for i, p in enumerate(politicians[:20], 1):
            name_link = link_cache.get(p["name"], p["name"])
            party_short = p["party"].replace("自由民主党・無所属の会", "自民").replace("立憲民主党・無所属", "立憲").replace("日本維新の会", "維新").replace("公明党", "公明").replace("自由民主党", "自民")
            house_short = p["house"].replace("衆議院", "衆").replace("参議院", "参").replace("両院", "衆参")
            rate_pct = f'{p["ambiguous_rate"]*100:.1f}%'
            lines.append(f'| {i} | {name_link} | {party_short} | {house_short} | {p["total_ambiguous"]:,} | {p["speech_count"]:,} | {rate_pct} | {p["top_word"]} |')
        lines.append('')

        # 使用率ランキング TOP10（発言100件以上）
        lines.append('## 使用率ランキング TOP10')
        lines.append('（最低発言数100件以上の議員のみ）')
        lines.append('')
        rate_ranking = [p for p in politicians if p["speech_count"] >= 100 and p["total_ambiguous"] > 0]
        rate_ranking.sort(key=lambda x: x["ambiguous_rate"], reverse=True)
        lines.append('| 順位 | 議員名 | 政党 | 使用率 | 使用回数/発言数 |')
        lines.append('|---:|---|---|---:|---|')
        for i, p in enumerate(rate_ranking[:10], 1):
            name_link = link_cache.get(p["name"], p["name"])
            if p["name"] not in link_cache:
                name_link = find_politician_link(p["name"], p["party"], p["house"])
            party_short = p["party"].replace("自由民主党・無所属の会", "自民").replace("立憲民主党・無所属", "立憲").replace("日本維新の会", "維新").replace("公明党", "公明").replace("自由民主党", "自民")
            rate_pct = f'{p["ambiguous_rate"]*100:.1f}%'
            lines.append(f'| {i} | {name_link} | {party_short} | {rate_pct} | {p["total_ambiguous"]:,}/{p["speech_count"]:,} |')
        lines.append('')

        # データについて
        lines.append('## データについて')
        lines.append('- 出典：国会議事録検索システム（国立国会図書館）★★★★★')
        lines.append('- 集計対象：第1回〜第218回国会')
        lines.append('- 集計日：2026年3月')
        lines.append(f'- 対象議員数：{detected_count:,}名')
        lines.append(f'- 総発言数：{total_speeches:,}件')
        lines.append('')

        # 書き出し
        md_content = "\n".join(lines)
        os.makedirs(os.path.dirname(OUTPUT_MD), exist_ok=True)
        with open(OUTPUT_MD, "w", encoding="utf-8") as f:
            f.write(md_content)

        print(f"  → {OUTPUT_MD}")
        print(f"  → {len(lines)} 行生成")
        print("=" * 60)
        print("[DONE] 曖昧語ランキングページ生成完了")
        print("=" * 60)

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    run()
