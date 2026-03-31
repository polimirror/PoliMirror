"""
PoliMirror - 献金×政策スタンス相関分析
v1.0.0

献金元を業界カテゴリに分類し、
献金を受けた議員の国会発言から政策スタンスを抽出する。
"""
import json
import os
import re
import traceback
from datetime import datetime

from dotenv import load_dotenv

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import anthropic

DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
SPEECHES_DIR = os.path.join(PROJECT_ROOT, "data", "speeches")
STANCES_DIR = os.path.join(PROJECT_ROOT, "data", "stances")
COMPANY_INDEX = os.path.join(DONATIONS_DIR, "company_index.json")

MODEL = "claude-haiku-4-5-20251001"

# 業界カテゴリ定義: カテゴリ名 → (キーワード, 政策テーマ, 発言検索キーワード)
INDUSTRY_CONFIG = {
    "自動車・製造業": {
        "donor_keywords": ["トヨタ", "自動車", "機連合", "電機連合", "ホンダ", "日産"],
        "policy_theme": "EV・自動車産業政策",
        "speech_keywords": ["EV", "電気自動車", "自動車産業", "カーボンニュートラル",
                            "脱炭素", "蓄電池", "水素", "モビリティ", "製造業"],
    },
    "電力・エネルギー": {
        "donor_keywords": ["電力", "電気", "エネルギー", "原子力", "電源"],
        "policy_theme": "原発・エネルギー政策",
        "speech_keywords": ["原発", "原子力", "再生可能エネルギー", "再エネ", "太陽光",
                            "風力", "電力自由化", "エネルギー安全保障", "GX"],
    },
    "医療・製薬": {
        "donor_keywords": ["医師", "医療", "病院", "薬", "製薬", "歯科"],
        "policy_theme": "医療費・社会保障政策",
        "speech_keywords": ["医療費", "診療報酬", "国民皆保険", "介護", "社会保障",
                            "医師不足", "地域医療", "薬価", "後期高齢者"],
    },
    "建設・不動産": {
        "donor_keywords": ["建設", "建託", "不動産", "住宅", "土木"],
        "policy_theme": "公共事業・インフラ政策",
        "speech_keywords": ["公共事業", "インフラ", "国土強靭化", "建設業", "道路",
                            "橋梁", "防災", "老朽化", "人手不足"],
    },
    "郵政・通信": {
        "donor_keywords": ["郵便", "郵政", "NTT", "通信"],
        "policy_theme": "郵政・通信政策",
        "speech_keywords": ["郵便局", "郵政民営化", "ユニバーサルサービス", "通信",
                            "デジタル", "5G", "情報通信"],
    },
}


def load_company_index():
    with open(COMPANY_INDEX, "r", encoding="utf-8") as f:
        return json.load(f)


def categorize_donors(company_index):
    """献金元を業界カテゴリに分類"""
    result = {}
    for cat_name, cfg in INDUSTRY_CONFIG.items():
        donors = []
        all_pols = set()
        for donor, entries in company_index.items():
            if any(kw in donor for kw in cfg["donor_keywords"]):
                pols = [e["politician"] for e in entries if e.get("politician_type") == "politician"]
                total = sum(e["amount"] for e in entries)
                donors.append({"name": donor, "amount": total, "politicians": pols})
                all_pols.update(pols)
        if donors:
            result[cat_name] = {
                "policy_theme": cfg["policy_theme"],
                "speech_keywords": cfg["speech_keywords"],
                "donors": sorted(donors, key=lambda x: -x["amount"]),
                "all_politicians": sorted(all_pols),
            }
    return result


def load_speeches(politician_name, keywords, max_speeches=20):
    """議員の発言からキーワードで絞り込み"""
    safe = politician_name.replace(" ", "")
    speech_dir = os.path.join(SPEECHES_DIR, safe)
    if not os.path.isdir(speech_dir):
        return []

    matched = []
    for year_dir in sorted(os.listdir(speech_dir), reverse=True):
        year_path = os.path.join(speech_dir, year_dir)
        if not os.path.isdir(year_path):
            continue
        for f in os.listdir(year_path):
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(year_path, f), "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                text = data.get("speech", "")
                if any(kw in text for kw in keywords):
                    matched.append({
                        "date": data.get("date", ""),
                        "meeting": data.get("nameOfMeeting", ""),
                        "speech": text[:2000],
                        "url": data.get("speechURL", ""),
                    })
                    if len(matched) >= max_speeches:
                        return matched
            except Exception:
                pass
    return matched


def analyze_stance(politician_name, policy_theme, speeches, client):
    """Claude APIで政策スタンスを判定"""
    if not speeches:
        return {"stance": "データ不足", "confidence": 0.0, "summary": "関連発言なし"}

    speech_text = "\n\n---\n\n".join([
        f"[{s['date']} {s['meeting']}]\n{s['speech']}" for s in speeches[:10]
    ])

    prompt = f"""以下の国会発言から、「{policy_theme}」に対するこの議員のスタンスを判定してください。
発言が少ない・関連性が低い場合は confidence を低くしてください。
JSONのみ返してください。

{{"stance": "強く推進/推進/中立/慎重/反対のいずれか", "confidence": 0.0-1.0, "summary": "根拠を1文で"}}

議員名: {politician_name}
政策テーマ: {policy_theme}
関連発言({len(speeches)}件):

{speech_text[:6000]}
"""

    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=256,
            system="国会議員の政策スタンスを発言から客観的に判定するアシスタントです。JSONのみ返してください。",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            return json.loads(m.group(0))
    except Exception:
        traceback.print_exc()

    return {"stance": "判定エラー", "confidence": 0.0, "summary": "API応答エラー"}


def run_analysis():
    print("=" * 60)
    print("PoliMirror - 献金×政策スタンス相関分析 v1.0.0")
    print("=" * 60)

    client = anthropic.Anthropic()
    company_index = load_company_index()
    categories = categorize_donors(company_index)

    print(f"\n業界カテゴリ: {len(categories)}")
    for cat, info in categories.items():
        print(f"  {cat}: {len(info['donors'])}社 -> {len(info['all_politicians'])}名")

    correlation = {}
    total_api_calls = 0

    for cat_name, info in categories.items():
        print(f"\n{'='*40}")
        print(f"[{cat_name}] {info['policy_theme']}")
        print(f"{'='*40}")

        politicians_data = []
        for pol_name in info["all_politicians"]:
            print(f"  {pol_name}: ", end="", flush=True)

            # 発言検索
            speeches = load_speeches(pol_name, info["speech_keywords"])
            if not speeches:
                print(f"発言0件 -> スキップ")
                politicians_data.append({
                    "name": pol_name,
                    "stance": "データ不足",
                    "confidence": 0.0,
                    "summary": "関連発言なし",
                    "speech_count": 0,
                })
                continue

            # Claude APIでスタンス判定
            result = analyze_stance(pol_name, info["policy_theme"], speeches, client)
            total_api_calls += 1

            print(f"{len(speeches)}件 -> {result['stance']} (conf={result.get('confidence', 0):.2f})")

            # 献金元・金額を追加
            donation_info = []
            for donor in info["donors"]:
                if pol_name in donor["politicians"]:
                    donation_info.append({"donor": donor["name"], "amount": donor["amount"]})

            politicians_data.append({
                "name": pol_name,
                "stance": result.get("stance", "不明"),
                "confidence": result.get("confidence", 0),
                "summary": result.get("summary", ""),
                "speech_count": len(speeches),
                "donations": donation_info,
            })

        # スタンス分布
        dist = {}
        for p in politicians_data:
            s = p["stance"]
            dist[s] = dist.get(s, 0) + 1

        correlation[cat_name] = {
            "policy_theme": info["policy_theme"],
            "donor_count": len(info["donors"]),
            "politician_count": len(info["all_politicians"]),
            "politicians": politicians_data,
            "stance_distribution": dist,
        }

    # 保存
    os.makedirs(STANCES_DIR, exist_ok=True)
    summary_path = os.path.join(STANCES_DIR, "correlation_summary.json")
    output = {
        "analyzed_at": datetime.now().isoformat(),
        "model": MODEL,
        "api_calls": total_api_calls,
        "categories": correlation,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"完了: {total_api_calls} API呼び出し")
    print(f"保存: {summary_path}")
    print(f"{'='*60}")

    return output


if __name__ == "__main__":
    run_analysis()
