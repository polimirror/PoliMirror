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


def _format_entry_industry(p):
    """業界カテゴリ用: 献金元+発言要約のエントリ"""
    donations_parts = []
    if p.get("donations"):
        for d in p["donations"]:
            donations_parts.append(f"{d['donor']}（{format_yen(d['amount'])}）")
    donations_str = "、".join(donations_parts) if donations_parts else "該当献金なし"

    summary = p.get("summary", "（要約なし）")
    confidence = p.get("confidence", 0)
    speech_count = p.get("speech_count", 0)

    if confidence >= 0.9:
        conf_label = "高い"
    elif confidence >= 0.7:
        conf_label = "中程度"
    else:
        conf_label = "低い"

    return f"""### {pol_link(p['name'])}

**献金元:** {donations_str}

**国会発言の傾向（{speech_count}件の関連発言を分析）:**
{summary}

**発言傾向:** {p['stance']}（判定確度: {conf_label}）"""


def _format_entry_speech_only(p):
    """発言一覧用: 献金元なし、発言要約のみ"""
    summary = p.get("summary", "（要約なし）")
    confidence = p.get("confidence", 0)
    speech_count = p.get("speech_count", 0)

    if confidence >= 0.9:
        conf_label = "高い"
    elif confidence >= 0.7:
        conf_label = "中程度"
    else:
        conf_label = "低い"

    # 献金データがある場合だけ付記
    donations_note = ""
    if p.get("donations"):
        parts = [f"{d['donor']}（{format_yen(d['amount'])}）" for d in p["donations"]]
        donations_note = f"\n\n**参考 — この議員の政治資金における主な献金元:** {'、'.join(parts)}"

    return f"""### {pol_link(p['name'])}

**国会発言の傾向（{speech_count}件の関連発言を分析）:**
{summary}

**発言傾向:** {p['stance']}（判定確度: {conf_label}）{donations_note}"""


def generate_speech_list_page(cat_name, data):
    """「政治資金全般」専用: 献金×スタンス相関ではなく、発言一覧ページとして生成"""
    theme = data["policy_theme"]
    pols = data["politicians"]

    valid = [p for p in pols if p.get("confidence", 0) >= 0.5]
    insufficient = [p for p in pols if p.get("confidence", 0) < 0.5]

    entries = [_format_entry_speech_only(p) for p in sorted(valid, key=lambda x: -x.get("confidence", 0))]

    insufficient_section = ""
    if insufficient:
        parts = [f"- **{p['name']}** — {p.get('summary', '関連発言なし')}" for p in insufficient]
        insufficient_section = f"""### 判定保留（関連発言が不足）

以下の議員は「{theme}」に関する国会発言が少なく、発言傾向を判定できなかった。

{chr(10).join(parts)}
"""

    content = f"""---
title: "政治資金の透明性に関する発言一覧"
---

## このページの内容

国会議員が「政治資金の透明性」について国会でどのような発言をしているかの一覧。

このページは他の業界別相関ページ（医療・建設など）とは性質が異なる。業界別ページは「特定業界からの献金を受けた議員がその業界の政策について何を言っているか」を並べたものだが、このページは業界を問わず「政治資金の透明性」という横断テーマでの発言を集めたもの。

**データの流れ:**
1. 国会議事録APIから「政治資金」「献金」「規正法」「透明性」等のキーワードを含む発言を抽出した
2. Claude API（claude-haiku-4-5-20251001）で発言内容を要約し、政策に対する発言傾向を判定した

**読み方:**
- 「国会発言の傾向」= 国会議事録に記録された発言のAI要約
- 「発言傾向」= 発言から読み取れる姿勢（推進=透明化を積極的に主張 / 慎重=現行制度維持寄り / 中立=言及はあるが方向性が不明確）
- 「参考 — 献金元」= 一部の議員について、収支報告書から判明した主な献金元を参考情報として付記

> [!note] 注意
> ここに掲載されている議員が特定業界から献金を受けているとは限らない。政治資金の透明性について国会で発言した議員の一覧であり、判断は読者に委ねる。

---

{(chr(10) + chr(10) + "---" + chr(10) + chr(10)).join(entries)}

---

{insufficient_section}---
*このページはPoliMirrorが国会議事録から自動生成したデータです。*
*出典: 国会議事録（国立国会図書館API）*
*分析モデル: Claude API（claude-haiku-4-5-20251001）*
"""
    return content


def generate_category_page(cat_name, data):
    """業界カテゴリごとの相関ページを生成"""
    # 政治資金全般は別テンプレート
    if cat_name == "政治資金全般":
        return generate_speech_list_page(cat_name, data)

    theme = data["policy_theme"]
    pols = data["politicians"]

    valid = [p for p in pols if p.get("confidence", 0) >= 0.5]
    insufficient = [p for p in pols if p.get("confidence", 0) < 0.5]

    entries = [_format_entry_industry(p) for p in sorted(valid, key=lambda x: -x.get("confidence", 0))]

    # 判定保留
    insufficient_section = ""
    if insufficient:
        parts = [f"- **{p['name']}** — {p.get('summary', '関連発言なし')}" for p in insufficient]
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
- 「判定確度」= 発言数と内容の明確さに基づくAI判定の信頼度

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
    industry_rows = []
    speech_list_link = ""
    for cat_name, data in categories.items():
        valid = sum(1 for p in data["politicians"] if p.get("confidence", 0) >= 0.5)
        total = data["politician_count"]
        if cat_name == "政治資金全般":
            speech_list_link = f"- [[correlations/{cat_name}|政治資金の透明性に関する発言一覧]]（{valid}名分析済み）"
        else:
            industry_rows.append(f"| [[correlations/{cat_name}|{cat_name}]] | {data['policy_theme']} | {valid}/{total}名 |")

    content = f"""---
title: "献金と政策の相関分析"
---

## 献金と政策の相関分析

### 業界別: 献金を受けた議員の関連政策発言

「ある業界から献金を受けた議員が、その業界に関連する政策テーマについて国会で何を発言しているか」を並べたページ群。

| 業界 | 分析した政策テーマ | 分析済み議員 |
|------|-------------------|-------------|
{chr(10).join(industry_rows)}

**このページ群でわかること:** 献金額と発言内容の対比（因果関係の主張ではなく、事実の並列）
**このページ群でわからないこと:** 献金が政策に影響したかどうか（それは読者が判断すること）

### テーマ別: 国会発言一覧

業界との紐付けではなく、特定の政策テーマについて国会で発言した議員の一覧。

{speech_list_link}

### データソースと分析方法

1. **献金データ**: 政治資金収支報告書（総務省/都道府県選管公開PDF）から企業・団体名を業界分類
2. **発言データ**: 国会議事録検索システムAPIから関連キーワードを含む発言を抽出
3. **発言分析**: Claude API（claude-haiku-4-5-20251001）で発言を要約し、発言傾向を判定
4. **品質基準**: 関連発言が少なく判定確度が低い議員は「判定保留」として分離

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
