"""
PoliMirror - 政治資金セクションMD追記
v1.0.0

data/donations/{name}/2023_structured.json の有効データを
各議員のMDファイルに「政治資金」セクションとして追記する。
"""
import json
import os
import traceback

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
POLITICIANS_DIR = os.path.join(PROJECT_ROOT, "quartz", "content", "politicians")

# 議員名 → MDファイルパスのマッピング
POLITICIAN_MD_MAP = {
    "林芳正": "衆議院/自民/林 芳正.md",
    "石破茂": "衆議院/自民/石破 茂.md",
    "茂木敏充": "衆議院/自民/茂木 敏充.md",
    "中野洋昌": "衆議院/中道/中野 洋昌.md",
    "浜口誠": "参議院/民主/浜口 誠.md",
}

SECTION_HEADER = "## 政治資金（2023年）"


def format_yen(amount):
    """円を万円表記に変換。1万未満はそのまま円表記。"""
    if amount is None:
        return "0円"
    amount = int(amount)
    if amount >= 10000:
        man = amount / 10000
        if man == int(man):
            return f"{int(man):,}万円"
        return f"{man:,.1f}万円"
    return f"{amount:,}円"


def build_section(name, data):
    """structured.json の data からMDセクションを生成する"""
    dd = data["data"]
    total_income = dd.get("total_income", 0) or 0
    total_expense = dd.get("total_expense", 0) or 0

    ind = dd.get("individual_donations", {})
    ind_amount = ind.get("total_amount", 0) or 0
    ind_count = ind.get("count", 0) or 0

    corps = dd.get("corporate_donations", [])
    groups = dd.get("group_donations", [])
    events = dd.get("party_events", [])

    corp_total = sum((c.get("amount", 0) or 0) for c in corps)
    grp_total = sum((g.get("amount", 0) or 0) for g in groups)
    evt_total = sum((e.get("income", 0) or 0) for e in events)

    # 個人献金比率
    ind_ratio = (ind_amount / total_income * 100) if total_income > 0 else 0

    lines = []
    lines.append(SECTION_HEADER)
    lines.append("")
    lines.append("> 出典：政治資金収支報告書（総務省）★★★★★")
    lines.append("> ⚠️ OCR解析のため一部数値に誤差がある場合があります")
    lines.append("")
    lines.append("| 項目 | 金額 |")
    lines.append("|------|------|")

    if total_income > 0:
        lines.append(f"| 収入総額 | {format_yen(total_income)} |")
    if total_expense > 0:
        lines.append(f"| 支出総額 | {format_yen(total_expense)} |")
    if ind_amount > 0:
        lines.append(f"| 個人献金 | {format_yen(ind_amount)}（{ind_count}件） |")
    if corp_total > 0:
        lines.append(f"| 企業献金 | {format_yen(corp_total)}（{len(corps)}件） |")
    if grp_total > 0:
        lines.append(f"| 団体献金 | {format_yen(grp_total)}（{len(groups)}件） |")
    if evt_total > 0:
        lines.append(f"| パーティー収入 | {format_yen(evt_total)}（{len(events)}件） |")

    # 個人献金比率
    if total_income > 0:
        lines.append("")
        lines.append("### 個人献金比率")
        lines.append(f"{ind_ratio:.1f}%（収入全体に占める割合）")

    # 主な企業・団体献金
    donations_list = []
    for c in corps:
        amt = c.get("amount", 0) or 0
        if amt > 0:
            donations_list.append((c.get("name", "不明"), amt))
    for g in groups:
        amt = g.get("amount", 0) or 0
        if amt > 0:
            donations_list.append((g.get("name", "不明"), amt))

    if donations_list:
        donations_list.sort(key=lambda x: x[1], reverse=True)
        lines.append("")
        lines.append("### 主な企業・団体献金")
        lines.append("| 献金元 | 金額 |")
        lines.append("|--------|------|")
        for donor_name, amt in donations_list[:10]:
            lines.append(f"| {donor_name} | {format_yen(amt)} |")

    # 主なパーティー
    if events:
        event_list = [(e.get("name", "不明"), e.get("income", 0) or 0) for e in events]
        event_list.sort(key=lambda x: x[1], reverse=True)
        valid_events = [(n, a) for n, a in event_list if a > 0]
        if valid_events:
            lines.append("")
            lines.append("### 主な政治資金パーティー")
            lines.append("| パーティー名 | 収入 |")
            lines.append("|--------------|------|")
            for evt_name, amt in valid_events[:5]:
                lines.append(f"| {evt_name} | {format_yen(amt)} |")

    lines.append("")
    return "\n".join(lines)


def append_section_to_md(md_path, section_text):
    """MDファイルに政治資金セクションを追記（既存セクションがあれば置換）"""
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 既存の「## 政治資金（2023年）」セクションを除去
    if SECTION_HEADER in content:
        before = content.split(SECTION_HEADER)[0].rstrip()
        after_header = content.split(SECTION_HEADER, 1)[1]
        next_section = after_header.find("\n## ")
        if next_section >= 0:
            after = after_header[next_section:]
        else:
            after = ""
        content = before + "\n\n" + after
        content = content.rstrip() + "\n"

    # 既存の「## 政治資金」プレースホルダーを置換
    placeholder = "## 政治資金\n\n*政治資金収支報告書から収集予定*"
    if placeholder in content:
        content = content.replace(placeholder, section_text.rstrip())
    else:
        # プレースホルダーがなければ末尾に追記
        content = content.rstrip() + "\n\n" + section_text

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    print("=" * 60)
    print("PoliMirror - 政治資金セクション MD追記 v1.0.0")
    print("=" * 60)

    updated = 0
    skipped = 0

    for name, md_rel in POLITICIAN_MD_MAP.items():
        md_path = os.path.join(POLITICIANS_DIR, md_rel)
        structured_path = os.path.join(DONATIONS_DIR, name, "2023_structured.json")

        print(f"\n[{name}]")

        if not os.path.exists(md_path):
            print(f"  MDファイルなし: {md_path}")
            skipped += 1
            continue

        if not os.path.exists(structured_path):
            print(f"  structured.jsonなし")
            skipped += 1
            continue

        try:
            with open(structured_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            dd = data["data"]
            total_income = dd.get("total_income", 0) or 0
            corps = dd.get("corporate_donations", [])
            groups = dd.get("group_donations", [])
            events = dd.get("party_events", [])

            has_data = total_income > 0 or corps or groups or events
            if not has_data:
                print(f"  有効データなし → スキップ")
                skipped += 1
                continue

            section = build_section(name, data)
            append_section_to_md(md_path, section)
            print(f"  -> {md_path}")
            updated += 1
        except Exception:
            traceback.print_exc()
            skipped += 1

    print(f"\n{'='*60}")
    print(f"完了: 更新{updated}件, スキップ{skipped}件")
    print(f"{'='*60}")
