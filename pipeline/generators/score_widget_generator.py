"""
PoliMirror - スコアウィジェット生成 v4.3.0

新レイアウト: 五角形レーダーチャート（大・単独行）→ 4指標カード → プログレスバー5軸
SVG: viewBox 500x500, 中心(250,250), 半径160, ラベル font-size 16
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

RENHO_DATA = {
    "name": "蓮舫", "yomi": "れんほう",
    "total_ambiguous": 2, "speech_count": 50,
    "ambiguous_rate": 0.04, "top_word": "しっかりと",
}

# 5軸の角度（度）と名前
AXES = [
    (270, "言行一致度"),
    (342, "数値的誠実さ"),
    (54,  "約束追跡率"),
    (126, "説明の具体性"),
    (198, "立場の安定性"),
]

CX, CY, R = 250, 250, 160


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
    """5軸スコアを算出: (言行一致, 数値的誠実さ, 約束追跡率, 説明の具体性, 立場の安定性)"""
    consistency = max(0, min(100, round(100 - rate * 100)))
    numerical = max(0, min(100, round(math.log10(max(speech_count, 1)) / math.log10(25000) * 100)))
    promise = 50  # 暫定
    specificity = max(0, min(100, round(100 - rate * 80)))
    stability = 50  # 暫定
    return [consistency, numerical, promise, specificity, stability]


def polar_to_xy(angle_deg, radius):
    """極座標→直交座標"""
    rad = math.radians(angle_deg)
    return CX + radius * math.cos(rad), CY + radius * math.sin(rad)


def pentagon_points(radius):
    """五角形の頂点座標文字列"""
    pts = [polar_to_xy(a, radius) for a, _ in AXES]
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def generate_svg(scores):
    """SVGレーダーチャートを生成 (viewBox 500x500, 中心250,250, 半径160)"""
    try:
        lines = []
        lines.append('<svg viewBox="0 0 500 500" width="100%" xmlns="http://www.w3.org/2000/svg" style="max-width:500px;display:block;margin:0 auto">')

        # 背景グリッド（4重五角形）
        for pct in [25, 50, 75, 100]:
            r = R * pct / 100
            lines.append(f'<polygon points="{pentagon_points(r)}" fill="none" stroke="#ddd" stroke-width="0.8"/>')

        # 軸線
        for angle, _ in AXES:
            ex, ey = polar_to_xy(angle, R)
            lines.append(f'<line x1="{CX}" y1="{CY}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#ddd" stroke-width="0.8"/>')

        # スコアポリゴン
        pts = []
        for i, (angle, _) in enumerate(AXES):
            r = scores[i] / 100 * R
            x, y = polar_to_xy(angle, r)
            pts.append(f"{x:.1f},{y:.1f}")
        pts_str = " ".join(pts)
        lines.append(f'<polygon points="{pts_str}" fill="rgba(24,95,165,0.15)" stroke="#185FA5" stroke-width="2"/>')

        # スコア点
        for i, (angle, _) in enumerate(AXES):
            r = scores[i] / 100 * R
            x, y = polar_to_xy(angle, r)
            color = "#185FA5" if i not in [2, 4] else "#aaa"
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"/>')

        # 軸ラベル（五角形の外側に余裕を持って配置: 半径+40px）
        label_r = R + 40
        for i, (angle, label) in enumerate(AXES):
            lx, ly = polar_to_xy(angle, label_r)
            anchor = "middle"
            if angle > 180 and angle < 360:
                if angle != 270:
                    anchor = "end"
            elif angle > 0 and angle < 180:
                if angle != 90:
                    anchor = "start"
            color = "#555" if i not in [2, 4] else "#aaa"
            lines.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-size="16" fill="{color}" dominant-baseline="central">{label}</text>')

        # 暫定表示
        lines.append(f'<text x="{CX}" y="490" text-anchor="middle" font-size="12" fill="#aaa">⚠️ 暫定値</text>')

        lines.append('</svg>')
        return "\n".join(lines)
    except Exception:
        traceback.print_exc()
        return ""


def bar_html(label, score, note, is_pending=False):
    """プログレスバー1行のHTML"""
    if is_pending:
        return f"""<div style="margin-bottom:10px">
<div style="font-size:15px"><span>{label}</span> <span style="color:#aaa">--</span></div>
<div style="background:#e8e8e4;border-radius:4px;height:8px;overflow:hidden"><div style="width:0%;height:100%;background:#ccc;border-radius:4px"></div></div>
<div style="font-size:13px;color:#aaa">{note}</div>
</div>"""
    color = "#1a4fa0" if score >= 60 else "#d4a017" if score >= 40 else "#c0392b"
    return f"""<div style="margin-bottom:10px">
<div style="font-size:15px"><span>{label}</span> <span style="font-weight:bold">{score}/100</span></div>
<div style="background:#e8e8e4;border-radius:4px;height:8px;overflow:hidden"><div style="width:{score}%;height:100%;background:{color};border-radius:4px"></div></div>
<div style="font-size:13px;color:#aaa">{note}</div>
</div>"""


def generate_widget(name, pol_data, rank, total_pol):
    """HTMLウィジェットを生成（縦積みレイアウト）"""
    try:
        rate = pol_data["ambiguous_rate"]
        speech_count = pol_data["speech_count"]
        total_amb = pol_data["total_ambiguous"]
        by_word = pol_data.get("by_word", {})

        # TOP3曖昧語を取得
        top3 = sorted(by_word.items(), key=lambda x: x[1], reverse=True)[:3]

        scores = calc_scores(rate, speech_count)
        rate_pct = f"{rate * 100:.1f}"

        svg = generate_svg(scores)

        bars = bar_html("言行一致度", scores[0], "曖昧語使用率から算出")
        bars += bar_html("数値的誠実さ", scores[1], f"発言数{speech_count:,}件から算出")
        bars += bar_html("約束追跡率", 0, "データ収集中", is_pending=True)
        bars += bar_html("説明の具体性", scores[3], "曖昧語分析から算出")
        bars += bar_html("立場の安定性", 0, "データ収集中", is_pending=True)

        # TOP3 HTML
        top3_spans = ""
        for i, (word, count) in enumerate(top3, 1):
            top3_spans += f'<span>{i}位「{word}」<span style="color:#888;font-size:12px"> {count:,}回</span></span>\n'

        top3_html = f"""<div style="margin:12px 0;padding:12px 16px;background:#f5f5f3;border-radius:8px">
<div style="font-size:13px;color:#888;margin-bottom:8px">よく使う曖昧語 TOP3</div>
<div style="display:flex;gap:8px;flex-wrap:wrap">
{top3_spans}</div>
</div>"""

        html = f"""## 誠実さスコア（暫定）

> ⚠️ このスコアは暫定値です。順次データを拡充します。

<p style="font-size:14px;color:#555;margin-bottom:12px;padding:10px 14px;background:#f9f9f7;border-left:3px solid #1a4fa0;border-radius:0 4px 4px 0">曖昧語とは「しっかりと」「適切に」「前向きに検討」など、具体的な数値・期限・行動を含まない国会答弁表現。使用率が高いほど、発言が抽象的な傾向がある。</p>

<div>
{svg}
</div>
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:16px 0">
<div style="background:#f5f5f3;border-radius:8px;padding:12px;text-align:center"><div style="font-size:14px;color:#888">曖昧語使用回数</div><div style="font-size:26px;font-weight:500">{total_amb:,}回</div></div>
<div style="background:#f5f5f3;border-radius:8px;padding:12px;text-align:center"><div style="font-size:14px;color:#888">全議員順位</div><div style="font-size:26px;font-weight:500">{rank}<span style="font-size:15px;color:#888">/{total_pol:,}</span></div></div>
<div style="background:#f5f5f3;border-radius:8px;padding:12px;text-align:center"><div style="font-size:14px;color:#888">使用率</div><div style="font-size:26px;font-weight:500">{rate_pct}%</div></div>
</div>
{top3_html}
<div style="margin-top:8px">
{bars}
</div>

"""
        return html
    except Exception:
        traceback.print_exc()
        return ""


def run():
    """メイン処理"""
    try:
        print("=" * 60)
        print("スコアウィジェット生成 v4.3.0")
        print("=" * 60)

        with open(RANKING_JSON, "r", encoding="utf-8") as f:
            ranking_data = json.load(f)

        politicians = ranking_data["politicians"]
        total_pol = len([p for p in politicians if p["total_ambiguous"] > 0])

        rank_map = {}
        for i, p in enumerate(politicians, 1):
            rank_map[p["name"]] = (i, p)

        renho_rank = sum(1 for p in politicians if p["total_ambiguous"] > RENHO_DATA["total_ambiguous"]) + 1
        rank_map["蓮舫"] = (renho_rank, RENHO_DATA)

        success = 0
        for name in TARGETS:
            print(f"\n[処理] {name}")

            md_path = find_md_file(name)
            if not md_path:
                print("  [SKIP] MDファイルなし")
                continue

            if name not in rank_map:
                print("  [SKIP] ランキングデータなし")
                continue

            rank, pol_data = rank_map[name]

            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()

            pattern = r"## 誠実さスコア（暫定）\n.*?(?=\n## |\Z)"
            if re.search(pattern, content, re.DOTALL):
                content = re.sub(pattern, "", content, flags=re.DOTALL)
                content = re.sub(r"\n{3,}", "\n\n", content)

            widget = generate_widget(name, pol_data, rank, total_pol)

            insert_point = "## 投票行動"
            if insert_point in content:
                content = content.replace(insert_point, widget + insert_point)
            else:
                content = content.rstrip() + "\n\n" + widget

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(content)

            scores = calc_scores(pol_data["ambiguous_rate"], pol_data["speech_count"])
            print(f"  [OK] → {os.path.basename(md_path)} [{scores[0]},{scores[1]},{scores[2]},{scores[3]},{scores[4]}]")
            success += 1

        print(f"\n[DONE] {success}名")
        print("=" * 60)

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    run()
