"""
PoliMirror - 政治団体名→議員名 AI推定
v1.0.0

未マッチの団体名2,975件をClaude APIに100件バッチで渡し、
対応する議員名を推定する。
"""
import json
import os
import re
import time
import traceback
from datetime import datetime

from dotenv import load_dotenv

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import anthropic

DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "processed")
RESOLVED_PATH = os.path.join(DONATIONS_DIR, "team_name_resolved.json")

MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 100


def load_unmatched_teams():
    """未マッチ団体名を収集"""
    matched_orgs = set()
    for d in os.listdir(DONATIONS_DIR):
        dp = os.path.join(DONATIONS_DIR, d)
        if not os.path.isdir(dp):
            continue
        for f in os.listdir(dp):
            if f.endswith("_structured.json"):
                try:
                    with open(os.path.join(dp, f), encoding="utf-8") as fh:
                        data = json.load(fh)
                    for org in data.get("matched_organizations", []):
                        matched_orgs.add(org)
                except Exception:
                    pass

    all_teams = set()
    for year in ["2022", "2023"]:
        idx_path = os.path.join(DONATIONS_DIR, f"pdf_index_{year}.json")
        if os.path.exists(idx_path):
            with open(idx_path, encoding="utf-8") as f:
                idx = json.load(f)["index"]
            all_teams.update(idx.keys())

    unmatched = sorted(all_teams - matched_orgs)
    return unmatched


def load_politician_names():
    """全議員名リスト"""
    path = os.path.join(PROCESSED_DIR, "all_politicians.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_batch(batch, politician_names, client):
    """100件バッチをClaude APIで推定"""
    batch_str = "\n".join(f"- {name}" for name in batch)
    pol_str = ", ".join(politician_names[:200])  # 先頭200名（トークン節約）

    prompt = f"""あなたは日本の政治資金収支報告書の専門家です。
以下は政治団体名のリストです。
議員名リストを参照し、各団体がどの議員の関連団体か推定してください。

ルール：
- 確信度が高い場合のみ回答する（70%未満はnullにする）
- 議員名リストにない名前は絶対に出力しない
- 1団体につき1議員のみ回答する
- 政党支部は党名ではなく支部長の議員名を推定する

出力形式（JSONのみ・余分なテキスト不要）：
[
  {{"team_name": "〇〇後援会", "politician": "山田太郎", "confidence": 0.85}},
  {{"team_name": "△△政策研究会", "politician": null, "confidence": 0.0}}
]

議員名リスト（一部）：
{pol_str}

団体名リスト（{len(batch)}件）：
{batch_str}
"""

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system="政治資金収支報告書の団体名から議員名を推定する専門家です。JSONのみ返してください。",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        # JSON配列を抽出
        m = re.search(r"\[[\s\S]*\]", raw)
        if m:
            results = json.loads(m.group(0))
            return results, resp.usage.input_tokens, resp.usage.output_tokens
    except Exception:
        traceback.print_exc()

    return [], 0, 0


if __name__ == "__main__":
    print("=" * 60)
    print("PoliMirror - 政治団体名→議員名 AI推定 v1.0.0")
    print(f"モデル: {MODEL}")
    print("=" * 60)

    client = anthropic.Anthropic()
    unmatched = load_unmatched_teams()
    pol_names = load_politician_names()

    print(f"\n未マッチ団体: {len(unmatched)}件")
    print(f"議員名リスト: {len(pol_names)}名")
    print(f"バッチサイズ: {BATCH_SIZE}")
    print(f"推定バッチ数: {(len(unmatched) + BATCH_SIZE - 1) // BATCH_SIZE}")

    all_results = []
    total_in = 0
    total_out = 0
    resolved_count = 0

    for i in range(0, len(unmatched), BATCH_SIZE):
        batch = unmatched[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(unmatched) + BATCH_SIZE - 1) // BATCH_SIZE

        results, tok_in, tok_out = resolve_batch(batch, pol_names, client)
        total_in += tok_in
        total_out += tok_out

        # confidence 0.7以上を有効としてカウント
        valid = [r for r in results if r.get("politician") and r.get("confidence", 0) >= 0.7]
        resolved_count += len(valid)
        all_results.extend(results)

        print(f"[{batch_num}/{total_batches}] {len(batch)}件 -> 有効{len(valid)}件 (累計{resolved_count}件)")

        if batch_num % 5 == 0:
            print(f"  API: {total_in:,}入力 + {total_out:,}出力トークン")

    # 保存
    valid_results = [r for r in all_results if r.get("politician") and r.get("confidence", 0) >= 0.7]

    output = {
        "resolved_at": datetime.now().isoformat(),
        "model": MODEL,
        "total_teams": len(unmatched),
        "total_resolved": len(valid_results),
        "tokens": {"input": total_in, "output": total_out},
        "results": valid_results,
        "all_results": all_results,
    }

    with open(RESOLVED_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"完了: {len(valid_results)}/{len(unmatched)}件推定 ({len(valid_results)/len(unmatched)*100:.1f}%)")
    print(f"API: {total_in:,}入力 + {total_out:,}出力トークン")
    cost = total_in / 1e6 * 0.80 + total_out / 1e6 * 4.00
    print(f"推定コスト: ${cost:.4f}")
    print(f"保存: {RESOLVED_PATH}")
    print(f"{'='*60}")
