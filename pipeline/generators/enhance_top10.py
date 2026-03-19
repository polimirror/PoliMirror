"""
PoliMirror - 上位議員ページ強化スクリプト v1.0.0

対象10名の議員ページに以下を追加:
- 曖昧語スコアセクション
- 誠実さスコア（暫定）セクション
"""
import json
import math
import os
import re
import sys
import traceback

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
RANKING_JSON = os.path.join(PROJECT_ROOT, "data", "processed", "ambiguous_ranking.json")
POLITICIANS_DIR = os.path.join(PROJECT_ROOT, "quartz", "content", "politicians")

# 対象議員（MDが存在する6名 + 蓮舫）
TARGETS = ["岸田文雄", "河野太郎", "小泉進次郎", "枝野幸男", "山本太郎", "石破茂", "高市早苗", "玉木雄一郎", "蓮舫"]


def find_md_file(name):
    """議員名からMDファイルパスを探す"""
    try:
        for root, _dirs, files in os.walk(POLITICIANS_DIR):
            for fname in files:
                if not fname.endswith('.md'):
                    continue
                # スペースなし名で比較
                basename = fname.replace('.md', '').replace(' ', '').replace('　', '')
                if basename == name:
                    return os.path.join(root, fname)
    except Exception:
        traceback.print_exc()
    return None


def load_ranking():
    """ランキングデータを読み込み"""
    try:
        with open(RANKING_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception:
        traceback.print_exc()
        return None


def generate_ambiguous_section(pol_data, rank, total_politicians):
    """曖昧語スコアセクションを生成"""
    try:
        lines = []
        lines.append('## 曖昧語スコア')
        lines.append('')
        lines.append('| 項目 | 数値 |')
        lines.append('|------|------|')
        lines.append(f'| 使用回数 | {pol_data["total_ambiguous"]:,}回 |')
        lines.append(f'| 全議員中の順位 | {rank}位 / {total_politicians:,}名中 |')
        rate_pct = f'{pol_data["ambiguous_rate"] * 100:.1f}%'
        lines.append(f'| 使用率 | {rate_pct} |')
        lines.append(f'| 最多使用語 | 「{pol_data["top_word"]}」 |')
        lines.append('')
        lines.append('[[rankings/曖昧語ランキング|▶ 全議員ランキングを見る]]')
        lines.append('')
        return '\n'.join(lines)
    except Exception:
        traceback.print_exc()
        return ''


def generate_honesty_section(pol_data):
    """誠実さスコア（暫定）セクションを生成"""
    try:
        rate = pol_data["ambiguous_rate"]
        speech_count = pol_data["speech_count"]

        # 暫定スコア算出
        consistency = max(0, min(100, round(100 - rate * 100)))
        numerical = max(0, min(100, round(math.log10(max(speech_count, 1)) * 25)))
        specificity = max(0, min(100, round(100 - rate * 80)))

        lines = []
        lines.append('## 誠実さスコア（暫定）')
        lines.append('')
        lines.append('> ⚠️ このスコアは暫定値です。順次データを拡充します。')
        lines.append('')
        lines.append('| 評価軸 | スコア | 備考 |')
        lines.append('|--------|--------|------|')
        lines.append(f'| 言行一致度 | {consistency}/100 | 曖昧語使用率から算出 |')
        lines.append(f'| 数値的誠実さ | {numerical}/100 | 発言数{speech_count:,}件から算出 |')
        lines.append('| 約束追跡率 | -- | データ収集中 |')
        lines.append(f'| 説明の具体性 | {specificity}/100 | 曖昧語分析から算出 |')
        lines.append('| 立場の安定性 | -- | データ収集中 |')
        lines.append('')
        return '\n'.join(lines)
    except Exception:
        traceback.print_exc()
        return ''


def insert_sections(md_content, ambiguous_section, honesty_section):
    """MDの「投票行動」セクションの前に挿入"""
    try:
        # 「## 投票行動」の前に挿入
        insert_point = '## 投票行動'
        if insert_point in md_content:
            return md_content.replace(insert_point, ambiguous_section + '\n' + honesty_section + '\n' + insert_point)

        # なければ末尾に追加
        return md_content.rstrip() + '\n\n' + ambiguous_section + '\n' + honesty_section
    except Exception:
        traceback.print_exc()
        return md_content


def run():
    """メイン処理"""
    try:
        print("=" * 60)
        print("議員ページ強化スクリプト v1.0.0")
        print("=" * 60)

        ranking_data = load_ranking()
        if not ranking_data:
            print("[ERROR] ランキングデータ読み込み失敗")
            return

        politicians = ranking_data["politicians"]
        total_politicians = len([p for p in politicians if p["total_ambiguous"] > 0])

        # ランキング位置を構築（name -> rank）
        rank_map = {}
        for i, p in enumerate(politicians, 1):
            rank_map[p["name"]] = (i, p)

        success = 0
        for name in TARGETS:
            print(f"\n[処理] {name}")

            md_path = find_md_file(name)
            if not md_path:
                print(f"  [SKIP] MDファイルなし")
                continue

            if name not in rank_map:
                print(f"  [SKIP] ランキングデータなし")
                # データなしでもセクションは追加しない
                continue

            rank, pol_data = rank_map[name]

            with open(md_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 既に追加済みならスキップ
            if '## 曖昧語スコア' in content:
                print(f"  [SKIP] 既に追加済み")
                continue

            ambiguous_section = generate_ambiguous_section(pol_data, rank, total_politicians)
            honesty_section = generate_honesty_section(pol_data)
            new_content = insert_sections(content, ambiguous_section, honesty_section)

            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            print(f"  [OK] 曖昧語スコア + 誠実さスコア追加 → {os.path.basename(md_path)}")
            print(f"       順位={rank}位, 使用回数={pol_data['total_ambiguous']:,}, rate={pol_data['ambiguous_rate']:.3f}")
            success += 1

        print(f"\n[DONE] {success}名のページを強化")
        print("=" * 60)

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    run()
