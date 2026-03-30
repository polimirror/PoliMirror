"""
PoliMirror - company_index + 献金元ページ再構築（年度別対応）
v2.0.0

全 data/donations/*/20XX_structured.json を読み込み、
年度別集計でcompany_index.jsonを再生成し、
quartz/content/donations/ のページを年度推移付きで再生成する。
"""
import json
import os
import re
import traceback
from datetime import datetime

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
DONATIONS_MD_DIR = os.path.join(PROJECT_ROOT, "quartz", "content", "donations")
COMPANY_INDEX_PATH = os.path.join(DONATIONS_DIR, "company_index.json")

POLITICIAN_LINK_MAP = {
    "林芳正": ("politicians/衆議院/自民/林 芳正", "自民"),
    "石破茂": ("politicians/衆議院/自民/石破 茂", "自民"),
    "茂木敏充": ("politicians/衆議院/自民/茂木 敏充", "自民"),
    "中野洋昌": ("politicians/衆議院/中道/中野 洋昌", "中道"),
    "浜口誠": ("politicians/参議院/民主/浜口 誠", "民主"),
}


def format_yen(amount):
    if not amount:
        return "0円"
    amount = int(amount)
    if amount >= 10000:
        man = amount / 10000
        return f"{int(man):,}万円" if man == int(man) else f"{man:,.1f}万円"
    return f"{amount:,}円"


def safe_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "", name).strip()


def collect_all_donations():
    """全structured.jsonを読み込んで献金エントリを収集"""
    entries = []
    for d in sorted(os.listdir(DONATIONS_DIR)):
        dir_path = os.path.join(DONATIONS_DIR, d)
        if not os.path.isdir(dir_path):
            continue
        for f in os.listdir(dir_path):
            if not f.endswith("_structured.json"):
                continue
            year = f.split("_")[0]
            try:
                with open(os.path.join(dir_path, f), "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                dd = data["data"]
                politician = data.get("name", d)
                p_type = data.get("type", "unknown")

                for c in dd.get("corporate_donations", []):
                    amt = c.get("amount", 0) or 0
                    if amt > 0:
                        entries.append({
                            "donor": c.get("name", "不明").strip(),
                            "politician": politician,
                            "politician_type": p_type,
                            "amount": amt,
                            "year": year,
                            "donation_type": "corporate",
                        })
                for g in dd.get("group_donations", []):
                    amt = g.get("amount", 0) or 0
                    if amt > 0:
                        entries.append({
                            "donor": g.get("name", "不明").strip(),
                            "politician": politician,
                            "politician_type": p_type,
                            "amount": amt,
                            "year": year,
                            "donation_type": "group",
                        })
            except Exception:
                traceback.print_exc()
    return entries


def build_company_index(entries):
    """企業→議員の逆引きインデックス構築（年度別）"""
    index = {}
    for e in entries:
        donor = e["donor"]
        if donor not in index:
            index[donor] = []
        index[donor].append({
            "politician": e["politician"],
            "politician_type": e["politician_type"],
            "amount": e["amount"],
            "year": e["year"],
            "donation_type": e["donation_type"],
        })

    with open(COMPANY_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    return index


def generate_md_pages(index):
    """献金元別MDページを生成（年度推移対応）"""
    os.makedirs(DONATIONS_MD_DIR, exist_ok=True)

    # 既存ページを削除して再生成
    for f in os.listdir(DONATIONS_MD_DIR):
        if f.endswith(".md"):
            os.remove(os.path.join(DONATIONS_MD_DIR, f))

    generated = 0
    for donor_name, entries in sorted(index.items(), key=lambda x: sum(e["amount"] for e in x[1]), reverse=True):
        fname = safe_filename(donor_name)
        if not fname:
            continue

        # 年度別に整理
        years = sorted(set(e["year"] for e in entries))
        total_amount = sum(e["amount"] for e in entries)

        rows = []
        for e in sorted(entries, key=lambda x: (-int(x["year"]), -x["amount"])):
            pol = e["politician"]
            link_info = POLITICIAN_LINK_MAP.get(pol)
            pol_link = f"[[{link_info[0]}|{pol}]]" if link_info and link_info[0] else pol
            party = link_info[1] if link_info else "不明"
            dtype = "企業" if e["donation_type"] == "corporate" else "団体"
            rows.append(f"| {e['year']} | {pol_link} | {format_yen(e['amount'])} | {party} | {dtype} |")

        year_label = "・".join(years) + "年"

        content = f"""---
title: "{donor_name}｜政治献金"
---

## {donor_name}の政治献金（{year_label}）

> 出典：政治資金収支報告書（総務省）★★★★★

| 年度 | 献金先 | 金額 | 政党 | 種別 |
|------|--------|------|------|------|
{chr(10).join(rows)}

**献金総額: {format_yen(total_amount)}**

---
*このページはPoliMirrorが政治資金収支報告書から自動生成したデータです。*
"""

        md_path = os.path.join(DONATIONS_MD_DIR, f"{fname}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
        generated += 1

    return generated


if __name__ == "__main__":
    print("=" * 60)
    print("PoliMirror - company_index 再構築 v2.0.0")
    print("=" * 60)

    entries = collect_all_donations()
    print(f"献金エントリ: {len(entries)}件")

    years = set(e["year"] for e in entries)
    for y in sorted(years):
        cnt = sum(1 for e in entries if e["year"] == y)
        print(f"  {y}年: {cnt}件")

    index = build_company_index(entries)
    print(f"企業・団体数: {len(index)}")

    generated = generate_md_pages(index)
    print(f"MDページ生成: {generated}件")

    print(f"\n{'='*60}")
    print(f"完了: {len(entries)}エントリ, {len(index)}企業・団体, {generated}ページ")
    print(f"{'='*60}")
