"""
PoliMirror - 献金×政策スタンス相関ページ生成
v2.0.0

変更点（v2.0.0）:
- テーブル廃止→議員ごとの読み物スタイルに変更
- AI判定根拠（summary）を全議員に表示
- 各指標の意味を冒頭で説明
- 「この表の読み方」セクション追加
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

    # confidence 0.5以上のみ表示
    valid = [p for p in pols if p.get("confidence", 0) >= 0.5]
    insufficient = [p for p in pols if p.get("confidence", 0) < 0.5]

    # 議員ごとのエントリ生成
    entries = []
    for p in sorted(valid, key=lambda x: -x.get("confidence", 0)):
        donations_parts = []
        if p.get("donations"):
            for d in p["donations"]:
                donations_parts.append(f"{d['donor']}（{format_yen(d['amount'])}）")
        donations_str = "、".join(donations_parts) if donations_parts else "該当献金なし"

        summary = p.get("summary", "（要約なし）")
        confidence = p.get("confidence", 0)
        speech_count = p.get("speech_count", 0)

        # 確信度を日本語に
        if confidence >= 0.9:
            conf_label = "高い"
        elif confidence >= 0.7:
            conf_label = "中程度"
        else:
            conf_label = "低い"

        entry = f"""### {pol_link(p['name'])}

**献金元:** {donations_str}

**国会発言の傾向（{speech_count}件の関連発言を分析）:**
{summary}

**発言傾向:** {p['stance']}（判定の確からしさ: {conf_label}）"""

        entries.append(entry)

    # 判定保留
    insufficient_section = ""
    if insufficient:
        parts = []
        for p in insufficient:
            reason = p.get("summary", "関連発言なし")
            parts.append(f"- **{p['name']}** — {reason}")
        insufficient_section = f"""### 判定保留（関連発言が不足）

以下の議員は{cat_name}からの献金記録があるが、「{theme}」に関する国会発言が少なく、発言傾向を判定できなかった。

{chr(10).join(parts)}
"""

    content = f"""---
title: "{cat_name}｜献金と政策スタンスの相関"
---

## このページの内容

「{cat_name}」業界から政治献金を受けた議員が、「{theme}」について国会でどのような発言をしているかを並べたページ。

**データの流れ:**
1. 政治資金収支報告書から「{cat_name}」に分類される企業・団体の献金先議員を特定した
2. その議員の国会発言（国会議事録API）から「{theme}」に関連するキーワードを含む発言を抽出した
3. Claude API（claude-haiku-4-5-20251001）で発言内容を要約し、政策に対する発言傾向を判定した

**読み方:**
- 「献金元」= 収支報告書に記載された、この業界からの寄附・会費等の事実
- 「国会発言の傾向」= 国会議事録に記録された発言のAI要約。議員が実際に何を言ったかの概要
- 「発言傾向」= 発言内容から読み取れる姿勢。「推進」「慎重」「中立」など。行動や法案提出の有無ではない
- 「判定の確からしさ」= 発言数と内容の明確さに基づくAI判定の信頼度

> [!note] 注意
> 献金を受けたことと政策スタンスの間に因果関係があるとは限らない。このページは収支報告書と議事録の事実を並べるのみであり、判断は読者に委ねる。

---

{(chr(10) + chr(10) + "---" + chr(10) + chr(10)).join(entries)}

---

{insufficient_section}---
*このページはPoliMirrorが政治資金収支報告書と国会議事録から自動生成したデータです。*
*出典: 政治資金収支報告書（総務省/都道府県選管）+ 国会議事録（国立国会図書館API）*
*分析モデル: Claude API（claude-haiku-4-5-20251001）*
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

業界別に「その業界から献金を受けた議員が、関連政策について国会でどう発言しているか」を一覧にしたページ群。

**このページ群でわかること:**
- ある業界から献金を受けている議員が、その業界に関連する政策テーマについて国会で何を発言しているか
- 献金額と発言内容の対比（因果関係の主張ではなく、事実の並列）

**このページ群でわからないこと:**
- 献金が政策に影響したかどうか（それは読者が判断すること）
- 議員の全体的な政策スタンス（ここでは特定テーマの発言のみ分析）

| 業界 | 分析した政策テーマ | 分析済み議員 |
|------|-------------------|-------------|
{chr(10).join(rows)}

### データソースと分析方法

1. **献金データ**: 政治資金収支報告書（総務省/都道府県選管公開PDF）から企業・団体名を業界分類
2. **発言データ**: 国会議事録検索システムAPIから関連キーワードを含む発言を抽出
3. **発言分析**: Claude API（claude-haiku-4-5-20251001）で発言を要約し、発言傾向を5段階で判定
4. **品質基準**: 関連発言が少なく判定の確からしさが低い議員は「判定保留」として分離

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
    print("PoliMirror - 献金×政策スタンス相関ページ生成 v2.0.0")
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
