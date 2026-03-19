"""
PoliMirror - スコアウィジェット生成 v1.0.0

対象議員MDの「誠実さスコア（暫定）」セクションを
Chart.jsレーダーチャート + プログレスバーのHTMLブロックに置き換える。
"""
import json
import math
import os
import re
import sys
import traceback

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
RANKING_JSON = os.path.join(PROJECT_ROOT, "data", "processed", "ambiguous_ranking.json")
POLITICIANS_DIR = os.path.join(PROJECT_ROOT, "quartz", "content", "politicians")

TARGETS = [
    "安倍晋三", "岸田文雄", "河野太郎", "小泉進次郎", "枝野幸男",
    "山本太郎", "蓮舫", "石破茂", "高市早苗", "玉木雄一郎",
]

# 蓮舫は50件のみ収集のため手動データ
RENHO_DATA = {
    "name": "蓮舫", "yomi": "れんほう",
    "total_ambiguous": 2, "speech_count": 50,
    "ambiguous_rate": 0.04, "top_word": "しっかりと",
}

ROMAJI_MAP = {
    "安倍晋三": "abe", "岸田文雄": "kishida", "河野太郎": "kono",
    "小泉進次郎": "koizumi", "枝野幸男": "edano", "山本太郎": "yamamoto",
    "蓮舫": "renho", "石破茂": "ishiba", "高市早苗": "takaichi",
    "玉木雄一郎": "tamaki",
}


def find_md_file(name):
    """議員名からMDファイルパスを探す"""
    try:
        for root, _dirs, files in os.walk(POLITICIANS_DIR):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                basename = fname.replace(".md", "").replace(" ", "").replace("　", "")
                if basename == name:
                    return os.path.join(root, fname)
    except Exception:
        traceback.print_exc()
    return None


def calc_scores(rate, speech_count):
    """5軸スコアを算出"""
    consistency = max(0, min(100, round(100 - rate * 100)))
    numerical = max(0, min(100, round(math.log10(max(speech_count, 1)) / math.log10(25000) * 100)))
    promise = 50  # 暫定
    specificity = max(0, min(100, round(100 - rate * 80)))
    stability = 50  # 暫定
    return consistency, numerical, promise, specificity, stability


def bar_html(label, score, note, is_pending=False):
    """プログレスバー1行のHTML"""
    if is_pending:
        return f"""<div style="margin-bottom:10px">
<div style="display:flex;justify-content:space-between;font-size:13px"><span>{label}</span><span style="color:#aaa">--</span></div>
<div style="background:#e8e8e4;border-radius:4px;height:8px;overflow:hidden"><div style="width:0%;height:100%;background:#ccc;border-radius:4px"></div></div>
<div style="font-size:11px;color:#aaa">{note}</div>
</div>"""
    color = "#1a4fa0" if score >= 60 else "#d4a017" if score >= 40 else "#c0392b"
    return f"""<div style="margin-bottom:10px">
<div style="display:flex;justify-content:space-between;font-size:13px"><span>{label}</span><span style="font-weight:bold">{score}/100</span></div>
<div style="background:#e8e8e4;border-radius:4px;height:8px;overflow:hidden"><div style="width:{score}%;height:100%;background:{color};border-radius:4px"></div></div>
<div style="font-size:11px;color:#aaa">{note}</div>
</div>"""


def generate_widget(name, pol_data, rank, total_pol):
    """HTMLウィジェットを生成"""
    try:
        rate = pol_data["ambiguous_rate"]
        speech_count = pol_data["speech_count"]
        total_amb = pol_data["total_ambiguous"]
        top_word = pol_data.get("top_word", "")
        romaji = ROMAJI_MAP.get(name, "unknown")

        c, n, p, s, st = calc_scores(rate, speech_count)
        rate_pct = f"{rate * 100:.1f}"

        bars = bar_html("言行一致度", c, "曖昧語使用率から算出")
        bars += bar_html("数値的誠実さ", n, f"発言数{speech_count:,}件から算出")
        bars += bar_html("約束追跡率", 0, "データ収集中", is_pending=True)
        bars += bar_html("説明の具体性", s, "曖昧語分析から算出")
        bars += bar_html("立場の安定性", 0, "データ収集中", is_pending=True)

        html = f"""## 誠実さスコア（暫定）

> ⚠️ このスコアは暫定値です。順次データを拡充します。

<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px">
<div style="background:#f0f0ec;padding:12px;border-radius:8px;text-align:center"><div style="font-size:11px;color:#888">曖昧語使用回数</div><div style="font-size:22px;font-weight:bold">{total_amb:,}</div></div>
<div style="background:#f0f0ec;padding:12px;border-radius:8px;text-align:center"><div style="font-size:11px;color:#888">全議員順位</div><div style="font-size:22px;font-weight:bold">{rank}<span style="font-size:13px;color:#888">/{total_pol:,}</span></div></div>
<div style="background:#f0f0ec;padding:12px;border-radius:8px;text-align:center"><div style="font-size:11px;color:#888">使用率</div><div style="font-size:22px;font-weight:bold">{rate_pct}%</div></div>
<div style="background:#f0f0ec;padding:12px;border-radius:8px;text-align:center"><div style="font-size:11px;color:#888">最多使用語</div><div style="font-size:16px;font-weight:bold">「{top_word}」</div></div>
</div>

{bars}

"""
        return html
    except Exception:
        traceback.print_exc()
        return ""


def run():
    """メイン処理"""
    try:
        print("=" * 60)
        print("スコアウィジェット生成 v1.0.0")
        print("=" * 60)

        with open(RANKING_JSON, "r", encoding="utf-8") as f:
            ranking_data = json.load(f)

        politicians = ranking_data["politicians"]
        total_pol = len([p for p in politicians if p["total_ambiguous"] > 0])

        # name -> (rank, data)
        rank_map = {}
        for i, p in enumerate(politicians, 1):
            rank_map[p["name"]] = (i, p)

        # 蓮舫は手動追加
        renho_rank = sum(1 for p in politicians if p["total_ambiguous"] > RENHO_DATA["total_ambiguous"]) + 1
        rank_map["蓮舫"] = (renho_rank, RENHO_DATA)

        success = 0
        for name in TARGETS:
            print(f"\n[処理] {name}")

            md_path = find_md_file(name)
            if not md_path:
                print(f"  [SKIP] MDファイルなし")
                continue

            if name not in rank_map:
                print(f"  [SKIP] ランキングデータなし")
                continue

            rank, pol_data = rank_map[name]

            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 既存の「誠実さスコア（暫定）」セクションを削除
            # パターン: ## 誠実さスコア（暫定） から次の ## まで
            pattern = r"## 誠実さスコア（暫定）\n.*?(?=\n## |\Z)"
            if re.search(pattern, content, re.DOTALL):
                content = re.sub(pattern, "", content, flags=re.DOTALL)
                # 余分な空行を整理
                content = re.sub(r"\n{3,}", "\n\n", content)

            # 新しいウィジェットを「## 投票行動」の前に挿入
            widget = generate_widget(name, pol_data, rank, total_pol)

            insert_point = "## 投票行動"
            if insert_point in content:
                content = content.replace(insert_point, widget + insert_point)
            else:
                content = content.rstrip() + "\n\n" + widget

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(content)

            c, n, p, s, st = calc_scores(pol_data["ambiguous_rate"], pol_data["speech_count"])
            print(f"  [OK] ウィジェット追加 → {os.path.basename(md_path)}")
            print(f"       スコア: 一致={c} 誠実={n} 具体={s}")
            success += 1

        print(f"\n[DONE] {success}名のページにウィジェット追加")
        print("=" * 60)

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    run()
