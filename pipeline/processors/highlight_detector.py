"""
PoliMirror - 政治資金 注目データ自動検出
v1.0.0

transactions.json と summary.json を Claude API に渡し、
有権者視点で注目すべきデータを最大5件抽出する。

使用法:
  python highlight_detector.py 西田昌司
  python highlight_detector.py --all  (全議員・指示待ち)
"""
import json
import os
import re
import sys
import traceback
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")), ".env"))

import anthropic

# === 定数 ===
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
POLITICIANS_DIR = os.path.join(PROJECT_ROOT, "quartz", "content", "politicians")

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """あなたは政治資金の透明性を促進するデータアナリストです。
事実に基づいた客観的な分析のみ行い、推測や誹謗は一切しません。
JSONのみ返してください。"""

USER_PROMPT_TEMPLATE = """以下は日本の国会議員「{politician}」の政治資金データです。
一般の有権者が「え、これは？」と感じるような
注目すべきデータを最大5件抽出してください。

判断基準：
- 前年比で異常な増減（2倍以上・半分以下）
- 特定の団体への突出した依存（収入の20%以上）
- 社会的に話題になった団体・企業との関係
- 一般感覚と乖離した金額規模
- 時事問題と関連する資金の動き

重要ルール：
- 事実のみ記述する（推測・憶測は禁止）
- 「疑惑」「問題」などの断定的な表現は避ける
- 数値は収支報告書の記載に基づく
- 出典を明記する

出力形式（JSONのみ・余分なテキスト不要）：
[
  {{
    "rank": 1,
    "title": "注目ポイントの見出し（20文字以内）",
    "fact": "事実を1〜2文で記述（数字・出典含む）",
    "why": "なぜ注目すべきか（1文・客観的に）",
    "severity": "high/medium/low"
  }}
]

=== サマリーデータ ===
{summary_json}

=== 2022年トランザクション（抜粋・収入のみ） ===
{transactions_2022}

=== 2023年トランザクション（抜粋・収入のみ） ===
{transactions_2023}
"""


def load_politician_data(politician_name):
    """議員の政治資金データを読み込む"""
    base = os.path.join(DONATIONS_DIR, politician_name)

    summary_path = os.path.join(base, "summary.json")
    t2022_path = os.path.join(base, "2022_transactions.json")
    t2023_path = os.path.join(base, "2023_transactions.json")

    if not os.path.exists(summary_path):
        print(f"[ERROR] summary.json が見つかりません: {summary_path}")
        return None, None, None

    with open(summary_path, encoding="utf-8") as f:
        summary = json.load(f)

    t2022 = None
    if os.path.exists(t2022_path):
        with open(t2022_path, encoding="utf-8") as f:
            t2022 = json.load(f)

    t2023 = None
    if os.path.exists(t2023_path):
        with open(t2023_path, encoding="utf-8") as f:
            t2023 = json.load(f)

    return summary, t2022, t2023


def extract_income_transactions(transactions_data, max_items=50):
    """収入トランザクションのみ抽出（API送信用に絞る）"""
    if not transactions_data:
        return "データなし"

    items = transactions_data.get("transactions", [])
    income = [t for t in items if t.get("record_type") == "収入"]
    # 金額順にソート
    income.sort(key=lambda x: x.get("amount", 0) or 0, reverse=True)
    return json.dumps(income[:max_items], ensure_ascii=False, indent=1)


def detect_highlights(politician_name, client):
    """Claude APIで注目データを検出する"""
    summary, t2022, t2023 = load_politician_data(politician_name)
    if not summary:
        return None

    prompt = USER_PROMPT_TEMPLATE.format(
        politician=politician_name,
        summary_json=json.dumps(summary, ensure_ascii=False, indent=2),
        transactions_2022=extract_income_transactions(t2022),
        transactions_2023=extract_income_transactions(t2023),
    )

    print(f"  API送信: {len(prompt):,}文字")

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        print(f"  API: {tokens_in}入力 + {tokens_out}出力トークン")

        # JSON配列を抽出
        json_match = re.search(r"\[[\s\S]*\]", raw)
        if not json_match:
            print(f"  [ERROR] JSONが見つかりません")
            print(f"  Raw: {raw[:300]}")
            return None

        highlights = json.loads(json_match.group(0))
        return highlights

    except json.JSONDecodeError as e:
        print(f"  [ERROR] JSON解析失敗: {e}")
        return None
    except Exception:
        traceback.print_exc()
        return None


def format_highlights_md(highlights):
    """注目データをMarkdown形式にフォーマットする"""
    if not highlights:
        return ""

    severity_icons = {
        "high": "🔴",
        "medium": "🟡",
        "low": "🔵",
    }

    lines = []
    lines.append("## 注目データ（自動検出）")
    lines.append("")
    lines.append("> 以下はClaude API（claude-haiku-4-5-20251001）が収支報告書データから")
    lines.append("> 自動検出した注目ポイントです。事実に基づく客観的な分析であり、")
    lines.append("> 違法性や不正を示唆するものではありません。")
    lines.append("")

    for h in highlights:
        icon = severity_icons.get(h.get("severity", "low"), "🔵")
        title = h.get("title", "")
        fact = h.get("fact", "")
        why = h.get("why", "")
        severity = h.get("severity", "low")

        if severity == "high":
            lines.append(f"### {icon} {title}")
            lines.append("")
            lines.append(f"**{fact}**")
        elif severity == "medium":
            lines.append(f"### {icon} {title}")
            lines.append("")
            lines.append(fact)
        else:
            lines.append(f"#### {icon} {title}")
            lines.append("")
            lines.append(fact)

        if why:
            lines.append(f"*{why}*")
        lines.append("")

    return "\n".join(lines)


def save_highlights(politician_name, highlights):
    """注目データをJSONとして保存する"""
    base = os.path.join(DONATIONS_DIR, politician_name)
    out_path = os.path.join(base, "highlights.json")

    output = {
        "politician": politician_name,
        "detected_at": datetime.now().isoformat(),
        "model": MODEL,
        "highlights": highlights,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  -> {out_path}")
    return out_path


if __name__ == "__main__":
    politician = sys.argv[1] if len(sys.argv) > 1 else "西田昌司"

    print("=" * 60)
    print(f"PoliMirror - 注目データ検出 v1.0.0")
    print(f"対象: {politician}")
    print(f"モデル: {MODEL}")
    print("=" * 60)

    client = anthropic.Anthropic()

    print(f"\n[{politician}] 注目データ検出中...")
    highlights = detect_highlights(politician, client)

    if not highlights:
        print("[ERROR] 注目データを検出できませんでした")
        sys.exit(1)

    # 保存
    save_highlights(politician, highlights)

    # 表示
    print(f"\n{'='*60}")
    print(f"検出結果: {len(highlights)}件")
    print(f"{'='*60}")
    for h in highlights:
        sev = h.get("severity", "?")
        print(f"\n  [{sev.upper()}] {h.get('title', '')}")
        print(f"  事実: {h.get('fact', '')}")
        print(f"  理由: {h.get('why', '')}")

    # Markdown出力
    md = format_highlights_md(highlights)
    print(f"\n{'='*60}")
    print("Markdown出力:")
    print(f"{'='*60}")
    print(md)
