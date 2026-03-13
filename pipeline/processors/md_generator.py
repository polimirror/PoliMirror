"""
PoliMirror - Markdownファイル生成
v2.0.0

政治家データからQuartz用Markdownファイルを生成する。
テンプレートファイル (pipeline/templates/politician_template.md) を読み込み、
プレースホルダーを置換して出力する。
"""
import glob
import json
import os
import re
import traceback
from datetime import date


# プロジェクトルート（このファイルから2階層上）
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
TEMPLATE_PATH = os.path.join(PROJECT_ROOT, "pipeline", "templates", "politician_template.md")
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "raw")
OUTPUT_BASE = os.path.join(PROJECT_ROOT, "quartz", "content", "politicians")


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


def render_template(template: str, member: dict) -> str:
    """テンプレートのプレースホルダーを議員データで置換する"""
    try:
        replacements = {
            "{{name_ja}}": member.get("name_ja", "不明"),
            "{{name_kana}}": member.get("name_kana", ""),
            "{{house}}": member.get("house", "不明"),
            "{{party}}": member.get("party", "不明"),
            "{{constituency}}": member.get("constituency", "不明"),
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

        return result
    except Exception:
        traceback.print_exc()
        raise


def process_members(
    members: list[dict],
    house_prefix: str,
    output_base: str,
    template: str,
) -> dict:
    """議員リストを処理してMarkdownファイルを生成する"""
    stats = {"success": 0, "fail": 0, "skip": 0}

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

            md_content = render_template(template, member)

            out_path = os.path.join(out_dir, f"{seq_id}.md")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(md_content)

            stats["success"] += 1

        except Exception:
            print(f"[FAIL] {seq_id} ({member.get('name_ja', '?')})")
            traceback.print_exc()
            stats["fail"] += 1

    return stats


def main():
    """メイン処理"""
    try:
        print("=" * 60)
        print("PoliMirror Markdown Generator v2.0.0")
        print("=" * 60)

        print(f"[INFO] データディレクトリ: {DATA_DIR}")
        print(f"[INFO] 出力先: {OUTPUT_BASE}")
        print(f"[INFO] テンプレート: {TEMPLATE_PATH}")
        print()

        template = load_template(TEMPLATE_PATH)

        total_stats = {"success": 0, "fail": 0, "skip": 0}

        # 衆議院
        shugiin_file = find_latest_json(os.path.join(DATA_DIR, "shugiin_members_*.json"))
        if shugiin_file:
            shugiin_members = load_members(shugiin_file)
            if shugiin_members:
                stats = process_members(shugiin_members, "shugiin", OUTPUT_BASE, template)
                for k in total_stats:
                    total_stats[k] += stats[k]
                print(f"[INFO] 衆議院: 成功={stats['success']} 失敗={stats['fail']} スキップ={stats['skip']}")
        else:
            print("[WARN] 衆議院データが見つかりません")

        print()

        # 参議院
        sangiin_file = find_latest_json(os.path.join(DATA_DIR, "sangiin_members_*.json"))
        if sangiin_file:
            sangiin_members = load_members(sangiin_file)
            if sangiin_members:
                stats = process_members(sangiin_members, "sangiin", OUTPUT_BASE, template)
                for k in total_stats:
                    total_stats[k] += stats[k]
                print(f"[INFO] 参議院: 成功={stats['success']} 失敗={stats['fail']} スキップ={stats['skip']}")
        else:
            print("[WARN] 参議院データが見つかりません")

        print()
        print("=" * 60)
        print(f"[RESULT] 合計: 成功={total_stats['success']} 失敗={total_stats['fail']} スキップ={total_stats['skip']}")
        print("=" * 60)

    except Exception:
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
