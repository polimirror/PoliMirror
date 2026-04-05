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
発言と資金データの事実を並べるだけです。
必ずJSON配列を返してください。理由や説明文は不要です。

出力例（別の議員のケース）:
[{"rank":1,"title":"政治改革発言と高額パーティー収入","speech":{"date":"2024-02-01","venue":"本会議","quote":"政治資金の透明性を高めるべき","source_url":"https://kokkai.ndl.go.jp/..."},"money":{"fact":"2023年パーティー収入2,100万円（総収入の44%）","source":"収支報告書"},"contradiction":"政治資金の透明化を主張する一方、パーティー収入が総収入の44%を占める。","severity":"medium"}]

後援会レベルの少額でも、発言テーマと関連する資金の動きがあれば対比として抽出すること。"""

USER_PROMPT_TEMPLATE = """以下は日本の国会議員「{politician}」の【国会発言】と【政治資金トランザクション明細】です。
発言内容と資金の動きに乖離があるケースを最大5件抽出してください。

照合パターン（1つでも該当すれば抽出）：
1. 政治改革・透明化・規正法改正を発言 → 本人の資金団体で高額収支がある
2. 特定業界に関する政策発言 → 同業界関連の団体から寄附・会費を受領
3. 財政規律・歳出削減を発言 → 政治資金の支出が大きい
4. 庶民・国民生活を発言 → パーティー収入・高額寄附に依存
5. 派閥批判・解消を発言 → 派閥関連団体との資金やり取り

重要：
- 完全な「矛盾」でなくても「興味深い対比」であれば抽出する
- 判定基準を緩めること：同じテーマについて発言と資金データの両方が存在すれば、対比として抽出する
- 例：政治改革を発言している議員が、パーティーや寄附で数百万円以上の収入がある → これは対比として抽出すべき
- 発言の具体的引用と資金の具体的金額を必ず含める
- 事実を並べるだけ（推測・憶測は禁止）
- severity: "high"=明確な矛盾, "medium"=注目すべき対比, "low"=軽微な対比
- 理由の説明は不要。JSON配列のみ返すこと。0件の場合のみ [] を返す

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

=== トランザクション明細（収入・支出の個別取引） ===
{transactions_json}

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


def load_financial_data(politician_name):
    """資金データを読み込む（新形式summary.json / 旧形式structured.json両対応）"""
    donations_base = os.path.join(DONATIONS_DIR, politician_name)

    # 新形式: summary.json
    summary_path = os.path.join(donations_base, "summary.json")
    if os.path.exists(summary_path):
        with open(summary_path, encoding="utf-8") as f:
            return json.load(f), "summary"

    # 旧形式: *_structured.json
    for fname in sorted(os.listdir(donations_base)):
        if fname.endswith("_structured.json"):
            with open(os.path.join(donations_base, fname), encoding="utf-8") as f:
                data = json.load(f)
            # 旧形式をサマリー風に変換
            d = data.get("data", {})
            converted = {
                "politician": data.get("name", politician_name),
                "year": data.get("year", "?"),
                "total_income": d.get("total_income", 0),
                "total_expense": d.get("total_expense", 0),
                "corporate_donations": d.get("corporate_donations", []),
                "group_donations": d.get("group_donations", []),
                "party_events": d.get("party_events", []),
                "individual_donations": d.get("individual_donations", {}),
            }
            return converted, "structured"

    return None, None


def load_transactions(politician_name, max_items=50):
    """トランザクション明細を読み込む（合計行を除外し、金額降順で上位を返す）"""
    donations_base = os.path.join(DONATIONS_DIR, politician_name)
    all_tx = []
    for fname in sorted(os.listdir(donations_base)):
        if not fname.endswith("_transactions.json"):
            continue
        try:
            with open(os.path.join(donations_base, fname), encoding="utf-8") as f:
                data = json.load(f)
            for t in data.get("transactions", []):
                if t.get("record_type") == "合計":
                    continue
                all_tx.append(t)
        except Exception:
            traceback.print_exc()

    # 金額降順でソート（大きな取引ほど矛盾検出に有用）
    all_tx.sort(key=lambda x: abs(x.get("amount", 0) or 0), reverse=True)
    return all_tx[:max_items]


def detect_contradictions(politician_name, client):
    """Claude APIで発言と資金の矛盾を検出する"""
    # Load financial data
    donations_base = os.path.join(DONATIONS_DIR, politician_name)
    highlights_path = os.path.join(donations_base, "highlights.json")

    summary, data_format = load_financial_data(politician_name)
    if not summary:
        print(f"  [SKIP] 資金データなし: {politician_name}")
        return None

    # Load transaction details
    transactions = load_transactions(politician_name)
    print(f"  トランザクション明細: {len(transactions)}件")

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

    if not transactions and data_format != "structured":
        print(f"  [WARN] トランザクション明細なし（サマリーのみ）")

    # Build prompt
    # Select 15 diverse speeches (different dates, keyword-rich first)
    seen_dates = set()
    speeches_selected = []
    for s in speeches:
        if s["date"] not in seen_dates and len(speeches_selected) < 15:
            speeches_selected.append(s)
            seen_dates.add(s["date"])

    speeches_compact = []
    for s in speeches_selected:
        speeches_compact.append({
            "date": s["date"],
            "meeting": s["meeting"],
            "url": s["url"],
            "speech": s["speech"][:300],
        })

    # Compact summary to reduce token count
    summary_compact = json.dumps(summary, ensure_ascii=False, indent=1)
    if len(summary_compact) > 3000:
        summary_compact = summary_compact[:3000] + "\n..."

    # Transaction details - compact format for API
    tx_compact = []
    for t in transactions:
        tx_compact.append({
            "type": t.get("record_type", ""),
            "cat": t.get("summary1", ""),
            "detail": t.get("summary2", ""),
            "amount": t.get("amount", 0),
            "date": t.get("date", ""),
            "org": t.get("organization", ""),
        })
    transactions_json = json.dumps(tx_compact, ensure_ascii=False, indent=1) if tx_compact else "[]"
    if len(transactions_json) > 4000:
        transactions_json = transactions_json[:4000] + "\n..."

    highlights_compact = json.dumps(highlights[:3], ensure_ascii=False, indent=1) if highlights else "[]"

    prompt = USER_PROMPT_TEMPLATE.format(
        politician=politician_name,
        summary_json=summary_compact,
        transactions_json=transactions_json,
        highlights_json=highlights_compact,
        speeches_json=json.dumps(speeches_compact, ensure_ascii=False, indent=1),
        speech_count=len(speeches),
    )

    print(f"  API送信: {len(prompt):,}文字 (発言{len(speeches_selected)}件)")

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
