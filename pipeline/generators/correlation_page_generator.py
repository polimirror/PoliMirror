"""
PoliMirror - 献金×政策スタンス相関ページ生成
v1.0.0
"""
import json
import os

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
STANCES_DIR = os.path.join(PROJECT_ROOT, "data", "stances")
CORRELATIONS_DIR = os.path.join(PROJECT_ROOT, "quartz", "content", "correlations")
INDEX_MD = os.path.join(PROJECT_ROOT, "quartz", "content", "index.md")

POLITICIAN_LINK_MAP = {
    "林芳正": "politicians/衆議院/自民/林 芳正",
    "石破茂": "politicians/衆議院/自民/石破 茂",
    "茂木敏充": "politicians/衆議院/自民/茂木 敏充",
    "中野洋昌": "politicians/衆議院/中道/中野 洋昌",
    "浜口誠": "politicians/参議院/民主/浜口 誠",
    "丸川珠代": "politicians/参議院/自民/丸川 珠代",
    "宮沢洋一": "politicians/参議院/自民/宮沢 洋一",
    "西田実仁": "politicians/参議院/中道/西田 実仁",
    "浅野哲": "politicians/衆議院/国民/浅野 哲",
}


def format_yen(amount):
    if not amount:
        return "0円"
    amount = int(amount)
    if amount >= 10000:
        man = amount / 10000
        return f"{int(man):,}万円" if man == int(man) else f"{man:,.1f}万円"
    return f"{amount:,}円"


def pol_link(name):
    path = POLITICIAN_LINK_MAP.get(name)
    if path:
        return f"[[{path}|{name}]]"
    return name


def generate_category_page(cat_name, data):
    """業界カテゴリごとの相関ページを生成"""
    theme = data["policy_theme"]
    pols = data["politicians"]
    dist = data["stance_distribution"]

    # confidence 0.5以上のみ表示
    valid = [p for p in pols if p.get("confidence", 0) >= 0.5]
    insufficient = [p for p in pols if p.get("confidence", 0) < 0.5]

    rows = []
    for p in sorted(valid, key=lambda x: -x.get("confidence", 0)):
        donations_str = ""
        if p.get("donations"):
            donations_str = ", ".join(f"{d['donor']}({format_yen(d['amount'])})" for d in p["donations"])
        rows.append(
            f"| {pol_link(p['name'])} | {p['stance']} | {p['confidence']:.2f} | {p['speech_count']}件 | {donations_str} |"
        )

    insufficient_list = ""
    if insufficient:
        names = ", ".join(p["name"] for p in insufficient)
        insufficient_list = f"\n**データ不足により判定保留**: {names}\n"

    dist_str = " / ".join(f"{k}: {v}名" for k, v in sorted(dist.items()) if k != "データ不足")

    content = f"""---
title: "{cat_name}｜献金と政策スタンスの相関"
---

## {cat_name}から献金を受けた議員の「{theme}」スタンス

> 出典：政治資金収支報告書（総務省/都道府県選管）+ 国会議事録（国立国会図書館）
> 分析モデル：Claude Haiku 4.5
> ⚠️ 発言の文脈によりスタンス判定に誤差がある場合があります

### スタンス分布
{dist_str}

### 議員別スタンス

| 議員名 | スタンス | 確信度 | 関連発言数 | 献金元（金額） |
|--------|----------|--------|------------|----------------|
{chr(10).join(rows)}
{insufficient_list}
---
*このページはPoliMirrorが政治資金収支報告書と国会議事録から自動生成したデータです。*
*スタンス判定はAI分析であり、議員本人の公式見解を代表するものではありません。*
"""
    return content


def generate_index_page(categories):
    """相関分析の一覧ページ"""
    rows = []
    for cat_name, data in categories.items():
        valid = sum(1 for p in data["politicians"] if p.get("confidence", 0) >= 0.5)
        total = data["politician_count"]
        rows.append(f"| [[correlations/{cat_name}|{cat_name}]] | {data['policy_theme']} | {valid}/{total}名 |")

    content = f"""---
title: "献金と政策の相関分析"
---

## 献金と政策の相関分析

> 政治資金収支報告書の献金データと国会議事録の発言データを
> AI分析で突き合わせ、業界別の政策スタンスを可視化します。

| 業界カテゴリ | 政策テーマ | 分析済み議員 |
|--------------|------------|-------------|
{chr(10).join(rows)}

### 分析方法
1. 政治資金収支報告書から企業・団体の献金先議員を特定
2. 国会議事録から関連政策キーワードを含む発言を抽出
3. Claude AI（Haiku）で発言内容からスタンスを5段階判定
4. 確信度0.5未満のデータは除外

### 注意事項
- スタンスはAI分析であり、議員の公式見解を代表しません
- 献金と政策スタンスの因果関係を主張するものではありません
- 事実データの並列表示を目的としています

---
*PoliMirror - 事実の鏡*
"""
    return content


def update_top_index(categories):
    """トップページに相関セクション追加"""
    with open(INDEX_MD, "r", encoding="utf-8") as f:
        content = f.read()

    section = "## 献金と政策の相関"
    if section in content:
        before = content.split(section)[0].rstrip()
        after_part = content.split(section, 1)[1]
        next_sec = after_part.find("\n## ")
        if next_sec >= 0:
            after = after_part[next_sec:]
        else:
            after = ""
        content = before + "\n" + after
        content = content.rstrip() + "\n"

    links = []
    for cat_name, data in categories.items():
        valid = sum(1 for p in data["politicians"] if p.get("confidence", 0) >= 0.5)
        links.append(f"- [[correlations/{cat_name}|{cat_name}]] — {data['policy_theme']}（{valid}名分析済み）")

    new_section = f"""
## 献金と政策の相関

{chr(10).join(links)}
- [[correlations/|全分析一覧]]
"""
    # 「つながり可視化」の前に挿入
    marker = "## つながり可視化"
    if marker in content:
        idx = content.index(marker)
        content = content[:idx] + new_section + "\n" + content[idx:]
    else:
        content = content.rstrip() + "\n" + new_section

    with open(INDEX_MD, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    print("=" * 60)
    print("PoliMirror - 献金×政策スタンス相関ページ生成 v1.0.0")
    print("=" * 60)

    with open(os.path.join(STANCES_DIR, "correlation_summary.json"), "r", encoding="utf-8") as f:
        summary = json.load(f)

    categories = summary["categories"]
    os.makedirs(CORRELATIONS_DIR, exist_ok=True)

    # カテゴリ別ページ生成
    generated = 0
    for cat_name, data in categories.items():
        content = generate_category_page(cat_name, data)
        path = os.path.join(CORRELATIONS_DIR, f"{cat_name}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        valid = sum(1 for p in data["politicians"] if p.get("confidence", 0) >= 0.5)
        print(f"  {cat_name}: {valid}名有効 -> {path}")
        generated += 1

    # index.md
    idx_content = generate_index_page(categories)
    idx_path = os.path.join(CORRELATIONS_DIR, "index.md")
    with open(idx_path, "w", encoding="utf-8") as f:
        f.write(idx_content)
    generated += 1
    print(f"  index.md -> {idx_path}")

    # トップページ更新
    update_top_index(categories)
    print(f"  index.md (top) 更新")

    print(f"\n{'='*60}")
    print(f"完了: {generated}ページ生成")
    print(f"{'='*60}")
