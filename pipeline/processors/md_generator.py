"""
PoliMirror - Markdownファイル生成
v3.0.0

政治家データからQuartz用Markdownファイルを生成する。
- テンプレートベースの議員ページ生成
- [[内部リンク]]による政党・都道府県・同僚議員の相互リンク
- 都道府県インデックスページの自動生成
"""
from __future__ import annotations

import glob
import json
import os
import re
import traceback
from collections import defaultdict
from datetime import date


# プロジェクトルート（このファイルから2階層上）
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
TEMPLATE_PATH = os.path.join(PROJECT_ROOT, "pipeline", "templates", "politician_template.md")
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "raw")
OUTPUT_BASE = os.path.join(PROJECT_ROOT, "quartz", "content", "politicians")
REGION_OUTPUT = os.path.join(PROJECT_ROOT, "quartz", "content", "地域")

# 都道府県リスト（選挙区から抽出するための正規表現用）
PREFECTURES = [
    "北海道", "青森", "岩手", "宮城", "秋田", "山形", "福島",
    "茨城", "栃木", "群馬", "埼玉", "千葉", "東京", "神奈川",
    "新潟", "富山", "石川", "福井", "山梨", "長野",
    "岐阜", "静岡", "愛知", "三重",
    "滋賀", "京都", "大阪", "兵庫", "奈良", "和歌山",
    "鳥取", "島根", "岡山", "広島", "山口",
    "徳島", "香川", "愛媛", "高知",
    "福岡", "佐賀", "長崎", "熊本", "大分", "宮崎", "鹿児島", "沖縄",
]


def load_template(path: str) -> str:
    """テンプレートファイルを読み込む"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            template = f.read()
        print(f"[INFO] テンプレート読み込み完了: {path}")
        return template
    except Exception:
        traceback.print_exc()
        raise


def find_latest_json(pattern: str) -> str | None:
    """globパターンにマッチする最新のJSONファイルを返す"""
    try:
        files = sorted(glob.glob(pattern))
        if not files:
            print(f"[WARN] パターンに該当するファイルなし: {pattern}")
            return None
        latest = files[-1]
        print(f"[INFO] 使用ファイル: {latest}")
        return latest
    except Exception:
        traceback.print_exc()
        return None


def load_members(filepath: str) -> list[dict]:
    """JSONファイルから議員リストを読み込む"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        members = data.get("members", [])
        print(f"[INFO] 読み込み完了: {len(members)}件 ({filepath})")
        return members
    except Exception:
        traceback.print_exc()
        return []


def extract_prefecture(constituency: str) -> str | None:
    """選挙区文字列から都道府県名を抽出する"""
    try:
        if not constituency:
            return None
        # （比）で始まるものはスキップ
        if constituency.startswith("（比）") or constituency == "比例":
            return None
        # 「鳥取・島根」「徳島・高知」のような合区 → 最初の方を返す
        for pref in PREFECTURES:
            if constituency.startswith(pref):
                return pref
        return None
    except Exception:
        traceback.print_exc()
        return None


def extract_all_prefectures(constituency: str) -> list[str]:
    """選挙区文字列から全ての都道府県名を抽出する（合区対応）"""
    try:
        if not constituency:
            return []
        if constituency.startswith("（比）") or constituency == "比例":
            return []
        found = []
        for pref in PREFECTURES:
            if pref in constituency:
                found.append(pref)
        return found
    except Exception:
        traceback.print_exc()
        return []


def build_tags(member: dict) -> str:
    """タグリストをテンプレート挿入用の文字列として生成する"""
    try:
        tags = []
        for field in ("house", "party"):
            val = member.get(field, "")
            if val:
                tags.append(val)

        constituency = member.get("constituency", "")
        if constituency:
            prefecture = re.sub(r"[0-9０-９（）\(\)比）]", "", constituency).strip()
            if prefecture:
                tags.append(prefecture)

        status = member.get("status", "")
        if status:
            tags.append(status)

        return ", ".join(f'"{t}"' for t in tags)
    except Exception:
        traceback.print_exc()
        return ""


def build_source_link(member: dict, field_name: str) -> str:
    """出典リンクを生成する。source_urlがあればMarkdownリンク、なければ「公式サイト」"""
    try:
        source_url = member.get("source_url", "")
        official_page = member.get("official_page", "")
        url = source_url or official_page
        if url:
            return f"[公式]({url})"
        return "公式サイト"
    except Exception:
        traceback.print_exc()
        return "公式サイト"


def add_wiki_links_to_constituency(constituency: str) -> str:
    """選挙区の都道府県部分を[[リンク]]に変換する"""
    try:
        if not constituency:
            return "不明"
        if constituency.startswith("（比）") or constituency == "比例":
            return constituency
        for pref in PREFECTURES:
            if pref in constituency:
                return constituency.replace(pref, f"[[{pref}]]", 1)
        return constituency
    except Exception:
        traceback.print_exc()
        return constituency


def build_party_section(member: dict, party_index: dict[str, list[dict]]) -> str:
    """同じ政党の議員セクションを生成する（最大10名、自分を除外）"""
    try:
        party = member.get("party", "")
        name = member.get("name_ja", "")
        if not party or party not in party_index:
            return ""

        colleagues = []
        for m in party_index[party]:
            if m.get("name_ja", "") != name:
                colleagues.append(m.get("name_ja", ""))
            if len(colleagues) >= 10:
                break

        if not colleagues:
            return ""

        lines = ["\n## 同じ政党の議員\n"]
        for c in colleagues:
            lines.append(f"- [[{c}]]")

        return "\n".join(lines)
    except Exception:
        traceback.print_exc()
        return ""


def render_template(template: str, member: dict, party_index: dict[str, list[dict]]) -> str:
    """テンプレートのプレースホルダーを議員データで置換する"""
    try:
        party = member.get("party", "不明")
        constituency = member.get("constituency", "不明")

        party_linked = f"[[{party}]]" if party and party != "不明" else "不明"
        constituency_linked = add_wiki_links_to_constituency(constituency)

        replacements = {
            "{{name_ja}}": member.get("name_ja", "不明"),
            "{{name_kana}}": member.get("name_kana", ""),
            "{{house}}": member.get("house", "不明"),
            "{{party}}": party,
            "{{party_linked}}": party_linked,
            "{{constituency}}": constituency,
            "{{constituency_linked}}": constituency_linked,
            "{{terms}}": str(member.get("terms", 0)),
            "{{status}}": member.get("status", "不明"),
            "{{last_updated}}": member.get("last_updated", str(date.today())),
            "{{tags}}": build_tags(member),
            "{{official_page}}": member.get("official_page", "") or "*未登録*",
            "{{website}}": member.get("website", "") or "*未登録*",
        }

        # 出典リンク（基本情報テーブルの各行）
        source_link = build_source_link(member, "source_url")
        for field in ("house", "party", "constituency", "terms", "status"):
            replacements[f"{{{{{field}_source}}}}"] = source_link

        result = template
        for placeholder, value in replacements.items():
            result = result.replace(placeholder, value)

        # 末尾に「同じ政党の議員」セクションを追加
        party_section = build_party_section(member, party_index)
        if party_section:
            result = result.rstrip() + "\n" + party_section + "\n"

        return result
    except Exception:
        traceback.print_exc()
        raise


def count_links(text: str) -> int:
    """テキスト中の[[リンク]]数をカウントする"""
    return len(re.findall(r"\[\[.+?\]\]", text))


def process_members(
    members: list[dict],
    house_prefix: str,
    output_base: str,
    template: str,
    party_index: dict[str, list[dict]],
) -> dict:
    """議員リストを処理してMarkdownファイルを生成する"""
    stats = {"success": 0, "fail": 0, "skip": 0, "links": 0}

    for i, member in enumerate(members, start=1):
        seq_id = f"{house_prefix}_{i:04d}"
        try:
            name = member.get("name_ja", "不明")
            party = member.get("party", "不明")
            house = member.get("house", "不明")

            if not name or name == "不明":
                print(f"[SKIP] {seq_id}: 名前が取得できないためスキップ")
                stats["skip"] += 1
                continue

            # 出力ディレクトリ: quartz/content/politicians/{house}/{party}/
            out_dir = os.path.join(output_base, house, party)
            os.makedirs(out_dir, exist_ok=True)

            md_content = render_template(template, member, party_index)
            stats["links"] += count_links(md_content)

            out_path = os.path.join(out_dir, f"{seq_id}.md")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(md_content)

            stats["success"] += 1

        except Exception:
            print(f"[FAIL] {seq_id} ({member.get('name_ja', '?')})")
            traceback.print_exc()
            stats["fail"] += 1

    return stats


def build_party_index(all_members: list[dict]) -> dict[str, list[dict]]:
    """全議員を政党別にインデックス化する"""
    try:
        index = defaultdict(list)
        for m in all_members:
            party = m.get("party", "")
            if party:
                index[party].append(m)
        print(f"[INFO] 政党インデックス構築: {len(index)}政党")
        return dict(index)
    except Exception:
        traceback.print_exc()
        return {}


def generate_prefecture_pages(all_members: list[dict]) -> dict:
    """都道府県インデックスページを生成する"""
    stats = {"pages": 0, "links": 0}
    try:
        # 都道府県別に議員を分類
        pref_members = defaultdict(lambda: {"衆議院": [], "参議院": []})

        for m in all_members:
            constituency = m.get("constituency", "")
            house = m.get("house", "")
            prefs = extract_all_prefectures(constituency)
            for pref in prefs:
                pref_members[pref][house].append(m)

        os.makedirs(REGION_OUTPUT, exist_ok=True)

        for pref in sorted(pref_members.keys()):
            houses = pref_members[pref]
            lines = [
                "---",
                f'title: "{pref}の議員"',
                f'tags: ["{pref}", "地域"]',
                "---",
                f"# {pref}の議員",
                "",
            ]

            link_count = 0
            for house_name in ("衆議院", "参議院"):
                members = houses.get(house_name, [])
                if not members:
                    continue
                lines.append(f"## {house_name}")
                lines.append("")
                for m in sorted(members, key=lambda x: x.get("name_kana", "")):
                    name = m.get("name_ja", "不明")
                    party = m.get("party", "不明")
                    constituency = m.get("constituency", "不明")
                    lines.append(f"- [[{name}]]（{party}・{constituency}）")
                    link_count += 1
                lines.append("")

            out_path = os.path.join(REGION_OUTPUT, f"{pref}.md")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            stats["pages"] += 1
            stats["links"] += link_count

        print(f"[INFO] 都道府県ページ生成: {stats['pages']}ページ, {stats['links']}リンク")
        return stats
    except Exception:
        traceback.print_exc()
        return stats


def main():
    """メイン処理"""
    try:
        print("=" * 60)
        print("PoliMirror Markdown Generator v3.0.0")
        print("=" * 60)

        print(f"[INFO] データディレクトリ: {DATA_DIR}")
        print(f"[INFO] 出力先: {OUTPUT_BASE}")
        print(f"[INFO] テンプレート: {TEMPLATE_PATH}")
        print()

        template = load_template(TEMPLATE_PATH)

        # 全議員データを読み込む
        all_members = []

        shugiin_file = find_latest_json(os.path.join(DATA_DIR, "shugiin_members_*.json"))
        shugiin_members = []
        if shugiin_file:
            shugiin_members = load_members(shugiin_file)
            all_members.extend(shugiin_members)

        sangiin_file = find_latest_json(os.path.join(DATA_DIR, "sangiin_members_*.json"))
        sangiin_members = []
        if sangiin_file:
            sangiin_members = load_members(sangiin_file)
            all_members.extend(sangiin_members)

        if not all_members:
            print("[ERROR] 議員データが見つかりません")
            return

        # 政党インデックスを構築（同じ政党の議員セクション用）
        party_index = build_party_index(all_members)

        total_stats = {"success": 0, "fail": 0, "skip": 0, "links": 0}

        # 衆議院
        if shugiin_members:
            stats = process_members(shugiin_members, "shugiin", OUTPUT_BASE, template, party_index)
            for k in total_stats:
                total_stats[k] += stats[k]
            print(f"[INFO] 衆議院: 成功={stats['success']} 失敗={stats['fail']} スキップ={stats['skip']} リンク={stats['links']}")
        else:
            print("[WARN] 衆議院データが見つかりません")

        print()

        # 参議院
        if sangiin_members:
            stats = process_members(sangiin_members, "sangiin", OUTPUT_BASE, template, party_index)
            for k in total_stats:
                total_stats[k] += stats[k]
            print(f"[INFO] 参議院: 成功={stats['success']} 失敗={stats['fail']} スキップ={stats['skip']} リンク={stats['links']}")
        else:
            print("[WARN] 参議院データが見つかりません")

        print()

        # 都道府県インデックスページ生成
        pref_stats = generate_prefecture_pages(all_members)
        total_stats["links"] += pref_stats["links"]

        print()
        print("=" * 60)
        print(f"[RESULT] 議員MD: 成功={total_stats['success']} 失敗={total_stats['fail']} スキップ={total_stats['skip']}")
        print(f"[RESULT] [[リンク]]総数: {total_stats['links']}")
        print(f"[RESULT] 都道府県ページ: {pref_stats['pages']}ページ")
        print("=" * 60)

    except Exception:
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
