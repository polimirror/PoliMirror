"""
PoliMirror - 政党支部名→議員名マッピング
v1.0.0

「自由民主党〇〇県第X選挙区支部」→ constituency_map から議員を特定。
"""
import json
import os
import re
import traceback

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "processed")
RESOLVED_PATH = os.path.join(DONATIONS_DIR, "branch_resolved.json")

# 政党名の正規化マップ
PARTY_MAP = {
    "自由民主党": "自民",
    "立憲民主党": "立憲",
    "日本維新の会": "維新",
    "公明党": "中道",  # MDでは「中道」
    "国民民主党": "国民",
    "日本共産党": "共産",
    "れいわ新選組": "れ新",
    "参政党": "参政",
    "社会民主党": "社民",
}

# 漢数字→算用数字
KANJI_NUM = {"一":"1","二":"2","三":"3","四":"4","五":"5","六":"6","七":"7","八":"8","九":"9","十":"10",
             "十一":"11","十二":"12","十三":"13","十四":"14","十五":"15","十六":"16","十七":"17","十八":"18","十九":"19","二十":"20"}


def parse_branch_name(branch_name):
    """支部名から政党・都道府県・選挙区番号を抽出"""
    # 政党名
    party = None
    for full, short in PARTY_MAP.items():
        if full in branch_name:
            party = short
            break
    if not party:
        return None

    # 都道府県（政党名の一部を誤認しないよう明示列挙）
    PREFS = ["北海道","青森","岩手","宮城","秋田","山形","福島","茨城","栃木","群馬",
             "埼玉","千葉","東京","神奈川","新潟","富山","石川","福井","山梨","長野",
             "岐阜","静岡","愛知","三重","滋賀","京都","大阪","兵庫","奈良","和歌山",
             "鳥取","島根","岡山","広島","山口","徳島","香川","愛媛","高知","福岡",
             "佐賀","長崎","熊本","大分","宮崎","鹿児島","沖縄"]
    pref = None
    for p in PREFS:
        if p in branch_name:
            pref = p
            break
    if not pref:
        return None

    # 「衆議院」or 「参議院」
    house = None
    if "衆議院" in branch_name:
        house = "衆議院"
    elif "参議院" in branch_name:
        house = "参議院"

    # 選挙区番号
    num = None
    # パターン1: 「第X選挙区」（漢数字）
    m = re.search(r"第([一二三四五六七八九十]+)選挙区", branch_name)
    if m:
        kanji = m.group(1)
        num = KANJI_NUM.get(kanji, kanji)
        house = house or "衆議院"
    # パターン2: 「第X選挙区」（算用数字）
    m2 = re.search(r"第?(\d+)選挙区", branch_name)
    if m2 and not num:
        num = m2.group(1)
        house = house or "衆議院"
    # パターン3: 「比例区第X」
    m3 = re.search(r"比例", branch_name)
    if m3:
        house = house or "参議院"
        return None  # 比例区支部は番号→議員の対応が不明

    if not num:
        return None

    return {"party": party, "pref": pref, "house": house, "num": num}


def match_branches():
    """全選挙区支部→議員名マッピング"""
    # constituency_map読み込み
    with open(os.path.join(PROCESSED_DIR, "constituency_map.json"), encoding="utf-8") as f:
        cmap = json.load(f)

    # 全インデックスから支部を収集
    branch_kw = ["選挙区支部", "選挙区第"]
    all_branches = {}  # branch_name -> {year: [urls]}

    for f in sorted(os.listdir(DONATIONS_DIR)):
        if f.startswith("pref_index_") and f.endswith(".json"):
            with open(os.path.join(DONATIONS_DIR, f), encoding="utf-8") as fh:
                idx = json.load(fh)
            year = re.search(r"_(\d{4})", f)
            yr = year.group(1) if year else "2023"
            for name, url in idx.items():
                if any(kw in name for kw in branch_kw):
                    if name not in all_branches:
                        all_branches[name] = {}
                    all_branches[name][yr] = url

        elif f.startswith("pdf_index_") and f.endswith(".json"):
            with open(os.path.join(DONATIONS_DIR, f), encoding="utf-8") as fh:
                data = json.load(fh)
            idx = data["index"]
            yr = data.get("year", f.replace("pdf_index_", "").replace(".json", ""))
            for name, urls in idx.items():
                if any(kw in name for kw in branch_kw):
                    if name not in all_branches:
                        all_branches[name] = {}
                    all_branches[name][yr] = urls

    # マッチング
    results = []
    matched = 0
    unmatched = 0
    ambiguous = 0

    for branch_name, year_urls in all_branches.items():
        parsed = parse_branch_name(branch_name)
        if not parsed:
            unmatched += 1
            continue

        # constituency_mapから候補検索
        candidates = []
        for pol_name, info in cmap.items():
            const = info["constituency"]
            pol_party = info["party"]

            # 政党一致
            if pol_party != parsed["party"]:
                continue

            # 都道府県+番号一致
            if parsed["pref"] in const and parsed["num"] in const:
                candidates.append(pol_name)

        if len(candidates) == 1:
            results.append({
                "branch_name": branch_name,
                "politician": candidates[0].replace(" ", ""),
                "politician_display": candidates[0],
                "confidence": 1.0,
                "parsed": parsed,
                "years": list(year_urls.keys()),
            })
            matched += 1
        elif len(candidates) > 1:
            ambiguous += 1
        else:
            unmatched += 1

    return results, matched, unmatched, ambiguous


if __name__ == "__main__":
    print("=" * 60)
    print("PoliMirror - 政党支部名→議員名マッピング v1.0.0")
    print("=" * 60)

    results, matched, unmatched, ambiguous = match_branches()

    print(f"\nマッチ: {matched}件")
    print(f"未マッチ: {unmatched}件（比例区・パース失敗）")
    print(f"複数候補（保留）: {ambiguous}件")

    # 保存
    output = {
        "total_matched": matched,
        "total_unmatched": unmatched,
        "total_ambiguous": ambiguous,
        "results": results,
    }
    with open(RESOLVED_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n保存: {RESOLVED_PATH}")
    print(f"\nサンプル20件:")
    for r in results[:20]:
        print(f"  {r['branch_name'][:40]:40s} -> {r['politician_display']}")
