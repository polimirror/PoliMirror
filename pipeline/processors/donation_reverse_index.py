"""
PoliMirror - 企業→議員 逆引きインデックス + 献金元MDページ生成
v1.0.0

STEP1: data/donations/*/2023_structured.json → company_index.json
STEP2: quartz/content/donations/{企業名}.md を生成
STEP3: index.md に「つながり可視化」セクション追加
"""
import json
import os
import re
import traceback

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
DONATIONS_MD_DIR = os.path.join(PROJECT_ROOT, "quartz", "content", "donations")
INDEX_MD_PATH = os.path.join(PROJECT_ROOT, "quartz", "content", "index.md")
COMPANY_INDEX_PATH = os.path.join(DONATIONS_DIR, "company_index.json")

# 議員名→MDリンク用パスのマッピング
POLITICIAN_LINK_MAP = {
    "林芳正": ("politicians/衆議院/自民/林 芳正", "自民"),
    "石破茂": ("politicians/衆議院/自民/石破 茂", "自民"),
    "茂木敏充": ("politicians/衆議院/自民/茂木 敏充", "自民"),
    "中野洋昌": ("politicians/衆議院/中道/中野 洋昌", "中道"),
    "浜口誠": ("politicians/参議院/民主/浜口 誠", "民主"),
    "立憲民主党": (None, "立憲"),
    "国民民主党": (None, "国民"),
    "日本共産党": (None, "共産"),
    "れいわ新選組": (None, "れいわ"),
    "日本維新の会": (None, "維新"),
}


def format_yen(amount):
    """円を万円表記に変換"""
    if not amount:
        return "0円"
    amount = int(amount)
    if amount >= 10000:
        man = amount / 10000
        if man == int(man):
            return f"{int(man):,}万円"
        return f"{man:,.1f}万円"
    return f"{amount:,}円"


def safe_filename(name):
    """ファイル名に使えない文字を除去"""
    return re.sub(r'[\\/:*?"<>|]', "", name).strip()


def step1_build_reverse_index():
    """STEP1: 全structured.jsonから企業→議員の逆引きインデックスを構築"""
    print("[STEP1] 逆引きインデックス構築")
    company_index = {}

    for d in sorted(os.listdir(DONATIONS_DIR)):
        p = os.path.join(DONATIONS_DIR, d, "2023_structured.json")
        if not os.path.isfile(p):
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            dd = data["data"]
            politician = data["name"]
            p_type = data.get("type", "unknown")

            # 企業献金
            for c in dd.get("corporate_donations", []):
                amt = c.get("amount", 0) or 0
                if amt <= 0:
                    continue
                donor = c.get("name", "不明").strip()
                if donor not in company_index:
                    company_index[donor] = []
                company_index[donor].append({
                    "politician": politician,
                    "politician_type": p_type,
                    "amount": amt,
                    "date": c.get("date"),
                    "year": 2023,
                    "donation_type": "corporate",
                })

            # 団体献金
            for g in dd.get("group_donations", []):
                amt = g.get("amount", 0) or 0
                if amt <= 0:
                    continue
                donor = g.get("name", "不明").strip()
                if donor not in company_index:
                    company_index[donor] = []
                company_index[donor].append({
                    "politician": politician,
                    "politician_type": p_type,
                    "amount": amt,
                    "date": g.get("date"),
                    "year": 2023,
                    "donation_type": "group",
                })
        except Exception:
            traceback.print_exc()

    # 保存
    with open(COMPANY_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(company_index, f, ensure_ascii=False, indent=2)

    total_entries = sum(len(v) for v in company_index.values())
    print(f"  {len(company_index)}企業・団体, {total_entries}件")
    print(f"  -> {COMPANY_INDEX_PATH}")
    return company_index


def step2_generate_md_pages(company_index):
    """STEP2: 企業ごとのMDページを生成"""
    print("\n[STEP2] 献金元別MDページ生成")
    os.makedirs(DONATIONS_MD_DIR, exist_ok=True)

    generated = 0
    for donor_name, entries in sorted(company_index.items(), key=lambda x: sum(e["amount"] for e in x[1]), reverse=True):
        total_amount = sum(e["amount"] for e in entries)
        fname = safe_filename(donor_name)
        if not fname:
            continue

        md_path = os.path.join(DONATIONS_MD_DIR, f"{fname}.md")

        # 献金先テーブル構築
        entries_sorted = sorted(entries, key=lambda x: x["amount"], reverse=True)
        rows = []
        for e in entries_sorted:
            pol = e["politician"]
            amt = format_yen(e["amount"])
            link_info = POLITICIAN_LINK_MAP.get(pol)
            if link_info and link_info[0]:
                pol_link = f"[[{link_info[0]}|{pol}]]"
                party = link_info[1]
            else:
                pol_link = pol
                party = link_info[1] if link_info else "不明"
            dtype = "企業" if e["donation_type"] == "corporate" else "団体"
            rows.append(f"| {pol_link} | {amt} | {party} | {dtype} |")

        content = f"""---
title: "{donor_name}｜政治献金"
---

## {donor_name}の政治献金（2023年）

> 出典：政治資金収支報告書（総務省）★★★★★

| 献金先 | 金額 | 政党 | 種別 |
|--------|------|------|------|
{chr(10).join(rows)}

**献金総額: {format_yen(total_amount)}**

---
*このページはPoliMirrorが政治資金収支報告書から自動生成したデータです。*
"""

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
        generated += 1

    print(f"  {generated}ページ生成")
    print(f"  -> {DONATIONS_MD_DIR}/")
    return generated


def step3_update_index_md(company_index):
    """STEP3: index.md に「つながり可視化」セクションを追加"""
    print("\n[STEP3] index.md 更新")

    with open(INDEX_MD_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    section_header = "## つながり可視化"

    # 既存セクションを除去
    if section_header in content:
        before = content.split(section_header)[0].rstrip()
        after_part = content.split(section_header, 1)[1]
        next_sec = after_part.find("\n## ")
        if next_sec >= 0:
            after = after_part[next_sec:]
        else:
            after = ""
        content = before + "\n" + after
        content = content.rstrip() + "\n"

    # 献金額TOP企業・団体を選出（議員個人への献金のみ、政党間は除外）
    top_donors = []
    for donor_name, entries in company_index.items():
        politician_entries = [e for e in entries if e["politician_type"] == "politician"]
        if not politician_entries:
            continue
        total = sum(e["amount"] for e in politician_entries)
        top_donors.append((donor_name, total, politician_entries))
    top_donors.sort(key=lambda x: x[1], reverse=True)

    # リンクリスト構築
    links = []
    for donor_name, total, entries in top_donors[:8]:
        fname = safe_filename(donor_name)
        pols = ", ".join(sorted(set(e["politician"] for e in entries)))
        links.append(f"- [[donations/{fname}|{donor_name}]] → {pols}")

    # 政党間の大口も追加
    party_donors = []
    for donor_name, entries in company_index.items():
        party_entries = [e for e in entries if e["politician_type"] == "party"]
        if not party_entries:
            continue
        total = sum(e["amount"] for e in party_entries)
        party_donors.append((donor_name, total, party_entries))
    party_donors.sort(key=lambda x: x[1], reverse=True)

    for donor_name, total, entries in party_donors[:4]:
        fname = safe_filename(donor_name)
        pols = ", ".join(sorted(set(e["politician"] for e in entries)))
        links.append(f"- [[donations/{fname}|{donor_name}]] → {pols}")

    new_section = f"""\n## つながり可視化

{chr(10).join(links)}
- 企業・団体献金データ収集中（現在{len(company_index)}件）
"""

    # 「政治資金ランキング ― *準備中*」の後に挿入
    insert_marker = "政治資金ランキング ― *準備中*"
    if insert_marker in content:
        idx = content.index(insert_marker) + len(insert_marker)
        content = content[:idx] + "\n" + new_section + content[idx:]
    else:
        content = content.rstrip() + "\n" + new_section

    with open(INDEX_MD_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"  -> {INDEX_MD_PATH}")


if __name__ == "__main__":
    print("=" * 60)
    print("PoliMirror - 献金逆引きインデックス + MDページ生成 v1.0.0")
    print("=" * 60)

    company_index = step1_build_reverse_index()
    generated = step2_generate_md_pages(company_index)
    step3_update_index_md(company_index)

    print(f"\n{'='*60}")
    print(f"完了: {len(company_index)}企業・団体, {generated}ページ生成")
    print(f"{'='*60}")
