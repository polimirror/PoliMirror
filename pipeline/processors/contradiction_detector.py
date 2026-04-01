"""
PoliMirror - 発言と資金の照合（矛盾検出）
v1.0.0

国会発言データと政治資金データをClaude APIで突き合わせ、
発言と資金の動きが矛盾・乖離しているケースを検出する。

使用法:
  python contradiction_detector.py 西田昌司
  python contradiction_detector.py 林芳正
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
SPEECHES_DIR = os.path.join(PROJECT_ROOT, "data", "speeches")

MODEL = "claude-haiku-4-5-20251001"

POLICY_KEYWORDS = [
    "政治資金", "献金", "パーティー", "透明", "改革", "規正", "企業献金",
    "財政", "税", "財務", "予算", "金融", "日銀", "庶民", "国民生活",
    "裏金", "説明責任", "政治とカネ", "清和", "派閥", "医療", "医師",
    "中小企業", "地方", "経済", "歳出", "国債",
]

SYSTEM_PROMPT = """あなたは政治データの照合を行うアナリストです。
事実のみを記述し、推測・憶測・断定は一切しません。
「〜と思われる」「〜の可能性がある」は使用禁止です。
発言と資金データの事実を並べるだけです。
JSONのみ返してください。"""

USER_PROMPT_TEMPLATE = """以下は日本の国会議員「{politician}」の【国会発言】と【政治資金データ】です。
発言内容と資金の実態が矛盾・乖離しているケースを最大5件抽出してください。

判断基準：
- 発言で主張していることと真逆の資金の動き
- 特定業界を批判しながらその業界から献金を受領
- 政治改革・透明化を訴えながらパーティー収入に依存
- 庶民目線を訴えながら高額パーティー開催
- 財政規律を主張しながら政治資金が膨張
- 特定団体・派閥を批判しながら同団体から資金受領

重要ルール：
- 事実のみ記述する（推測・憶測は禁止）
- 「〜と思われる」「〜の可能性がある」は使用禁止
- 発言と資金データの事実を並べるだけ
- 該当がなければ空配列 [] を返す

出力形式（JSONのみ・余分なテキスト不要）：
[
  {{
    "rank": 1,
    "title": "矛盾の見出し（25文字以内）",
    "speech": {{
      "date": "発言日（YYYY-MM-DD）",
      "venue": "委員会名等",
      "quote": "該当発言の引用（50文字以内・原文ママ）",
      "source_url": "国会議事録URL"
    }},
    "money": {{
      "fact": "資金データの事実（数字付き）",
      "source": "収支報告書の出典"
    }},
    "contradiction": "矛盾の説明（2文以内・事実を並べるだけ）",
    "severity": "high/medium/low"
  }}
]

=== 政治資金サマリー ===
{summary_json}

=== 注目データ（自動検出済み） ===
{highlights_json}

=== 国会発言（政策関連・{speech_count}件から抽出） ===
{speeches_json}
"""


def load_policy_speeches(politician_name, target_years=None, max_speeches=80):
    """政策関連の発言を抽出する"""
    base = os.path.join(SPEECHES_DIR, politician_name)
    if not os.path.isdir(base):
        print(f"  [ERROR] 発言ディレクトリなし: {base}")
        return []

    if target_years is None:
        target_years = ["2022", "2023", "2024", "2025"]

    speeches = []
    for year in sorted(os.listdir(base)):
        if target_years and year not in target_years:
            continue
        ypath = os.path.join(base, year)
        if not os.path.isdir(ypath):
            continue
        for fname in sorted(os.listdir(ypath)):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(ypath, fname), encoding="utf-8") as f:
                    d = json.load(f)
                speech_text = d.get("speech", "")
                # Skip short procedural speeches
                if len(speech_text) < 200:
                    continue
                if "散会" in speech_text[:80] or "御異議ない" in speech_text[:80]:
                    continue
                # Check keywords
                matched = [kw for kw in POLICY_KEYWORDS if kw in speech_text]
                if not matched:
                    continue
                speeches.append({
                    "date": d.get("date"),
                    "meeting": d.get("nameOfMeeting"),
                    "url": d.get("speechURL"),
                    "keywords": matched,
                    "speech": speech_text[:500],  # Truncate for API
                })
            except Exception:
                traceback.print_exc()

    # Sort by keyword relevance (more keywords = more relevant)
    speeches.sort(key=lambda x: len(x["keywords"]), reverse=True)
    return speeches[:max_speeches]


def detect_contradictions(politician_name, client):
    """Claude APIで発言と資金の矛盾を検出する"""
    # Load financial data
    donations_base = os.path.join(DONATIONS_DIR, politician_name)
    summary_path = os.path.join(donations_base, "summary.json")
    highlights_path = os.path.join(donations_base, "highlights.json")

    if not os.path.exists(summary_path):
        print(f"  [ERROR] summary.json なし: {summary_path}")
        return None

    with open(summary_path, encoding="utf-8") as f:
        summary = json.load(f)

    highlights = []
    if os.path.exists(highlights_path):
        with open(highlights_path, encoding="utf-8") as f:
            highlights = json.load(f).get("highlights", [])

    # Load speeches
    print(f"  発言データ読み込み中...")
    speeches = load_policy_speeches(politician_name)
    print(f"  政策関連発言: {len(speeches)}件")

    if not speeches:
        print(f"  [WARN] 政策関連発言が見つかりません")
        return None

    # Build prompt
    # Compact speeches for API
    speeches_compact = []
    for s in speeches:
        speeches_compact.append({
            "date": s["date"],
            "meeting": s["meeting"],
            "url": s["url"],
            "speech": s["speech"][:400],
        })

    prompt = USER_PROMPT_TEMPLATE.format(
        politician=politician_name,
        summary_json=json.dumps(summary, ensure_ascii=False, indent=1),
        highlights_json=json.dumps(highlights, ensure_ascii=False, indent=1),
        speeches_json=json.dumps(speeches_compact, ensure_ascii=False, indent=1),
        speech_count=len(speeches),
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
            print(f"  [WARN] JSONが見つかりません (矛盾なし?)")
            print(f"  Raw: {raw[:300]}")
            return []

        results = json.loads(json_match.group(0))
        return results

    except json.JSONDecodeError as e:
        print(f"  [ERROR] JSON解析失敗: {e}")
        return None
    except Exception:
        traceback.print_exc()
        return None


def format_contradictions_md(contradictions):
    """矛盾検出結果をMarkdown形式にフォーマットする"""
    if not contradictions:
        return ""

    severity_icons = {"high": "🔴", "medium": "🟡", "low": "🔵"}

    lines = []
    lines.append("## 発言と資金の照合")
    lines.append("")
    lines.append("> 以下はClaude API（claude-haiku-4-5-20251001）が国会発言と収支報告書データを")
    lines.append("> 照合した結果です。事実を並べるのみであり、違法性の断定ではありません。")
    lines.append("> 解釈は読者に委ねます。")
    lines.append("")

    for c in contradictions:
        icon = severity_icons.get(c.get("severity", "low"), "🔵")
        title = c.get("title", "")
        speech = c.get("speech", {})
        money = c.get("money", {})
        contradiction = c.get("contradiction", "")
        severity = c.get("severity", "low")

        if severity == "high":
            lines.append(f"### {icon} {title}")
        else:
            lines.append(f"### {icon} {title}")
        lines.append("")

        # Speech quote
        quote = speech.get("quote", "")
        date = speech.get("date", "")
        venue = speech.get("venue", "")
        url = speech.get("source_url", "")

        if url:
            lines.append(f"**発言（{date}・{venue}）：**")
            lines.append(f'> 「{quote}」')
            lines.append(f"出典: [国会議事録]({url})")
        else:
            lines.append(f"**発言（{date}・{venue}）：**")
            lines.append(f'> 「{quote}」')
        lines.append("")

        # Money fact
        money_fact = money.get("fact", "")
        money_source = money.get("source", "")
        lines.append(f"**同時期の資金データ：**")
        lines.append(f"{money_fact}")
        if money_source:
            lines.append(f"出典: {money_source}")
        lines.append("")

        if contradiction:
            lines.append(f"*{contradiction}*")
            lines.append("")

    return "\n".join(lines)


def save_contradictions(politician_name, contradictions):
    """矛盾検出結果をJSONとして保存する"""
    base = os.path.join(DONATIONS_DIR, politician_name)
    out_path = os.path.join(base, "contradictions.json")

    output = {
        "politician": politician_name,
        "detected_at": datetime.now().isoformat(),
        "model": MODEL,
        "contradictions": contradictions,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  -> {out_path}")
    return out_path


if __name__ == "__main__":
    politician = sys.argv[1] if len(sys.argv) > 1 else "西田昌司"

    print("=" * 60)
    print(f"PoliMirror - 発言と資金の照合 v1.0.0")
    print(f"対象: {politician}")
    print(f"モデル: {MODEL}")
    print("=" * 60)

    client = anthropic.Anthropic()

    print(f"\n[{politician}] 矛盾検出中...")
    contradictions = detect_contradictions(politician, client)

    if contradictions is None:
        print("[ERROR] 検出処理に失敗しました")
        sys.exit(1)

    if not contradictions:
        print("[INFO] 矛盾は検出されませんでした")
        save_contradictions(politician, [])
        sys.exit(0)

    # 保存
    save_contradictions(politician, contradictions)

    # 表示
    print(f"\n{'='*60}")
    print(f"検出結果: {len(contradictions)}件")
    print(f"{'='*60}")
    for c in contradictions:
        sev = c.get("severity", "?")
        print(f"\n  [{sev.upper()}] {c.get('title', '')}")
        sp = c.get("speech", {})
        print(f"  発言: {sp.get('date', '')} {sp.get('venue', '')}")
        print(f"  引用: 「{sp.get('quote', '')}」")
        print(f"  URL: {sp.get('source_url', 'なし')}")
        mn = c.get("money", {})
        print(f"  資金: {mn.get('fact', '')}")
        print(f"  照合: {c.get('contradiction', '')}")

    # Markdown出力
    md = format_contradictions_md(contradictions)
    print(f"\n{'='*60}")
    print("Markdown出力:")
    print(f"{'='*60}")
    print(md)
