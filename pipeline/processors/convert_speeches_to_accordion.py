"""
PoliMirror - 発言セクション二重アコーディオン化 v2.0.0

「## 発言・活動記録」セクション全体を外側<details>で包み、
内側の個別発言<details>と合わせて二重アコーディオン構造にする。
既に個別アコーディオン化済みの<details>タグはそのまま活用。
個別発言のスタイルも新仕様に更新。
"""
import os
import re
import sys
import traceback

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
POLITICIANS_DIR = os.path.join(PROJECT_ROOT, "quartz", "content", "politicians")

TARGETS = [
    "安倍晋三", "岸田文雄", "河野太郎", "小泉進次郎", "枝野幸男",
    "山本太郎", "蓮舫", "石破茂", "高市早苗", "玉木雄一郎",
]


def find_md_file(name):
    """議員名からMDファイルパスを探す"""
    try:
        for root, _dirs, files in os.walk(POLITICIANS_DIR):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                basename = fname.replace(".md", "").replace(" ", "").replace("　", "")
                if basename == name:
                    return os.path.join(root, fname)
    except Exception:
        traceback.print_exc()
    return None


def update_inner_details_style(details_html):
    """個別発言<details>のスタイルを新仕様に更新"""
    try:
        # summary のスタイルを更新
        details_html = re.sub(
            r'<details>\s*\n<summary style="[^"]*">',
            '<details style="margin:0">\n<summary style="cursor:pointer;padding:8px 4px;border-bottom:1px solid #e5e5e3;list-style:none;display:flex;justify-content:space-between">',
            details_html
        )
        # span のスタイルを更新（タイトル側）
        details_html = re.sub(
            r'<span style="font-size:14px;font-weight:500;color:#1a1a1a">',
            '<span style="font-size:14px">',
            details_html
        )
        # div のスタイルを更新（コンテンツ側）
        details_html = re.sub(
            r'<div style="padding:12px 0 16px;border-bottom:1px solid #f0f0ee">',
            '<div style="padding:12px 8px 16px;background:#fafaf8">',
            details_html
        )
        return details_html
    except Exception:
        traceback.print_exc()
        return details_html


def wrap_section(md_path):
    """発言セクション全体を外側アコーディオンで包む"""
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 「## 発言・活動記録」から次の「## 」までを抽出
        pattern = r'(## 発言・活動記録)\n(.*?)(?=\n## |\Z)'
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            print("  [SKIP] 発言セクションなし")
            return 0

        section_body = match.group(2).strip()

        # 個別<details>の件数をカウント
        count = len(re.findall(r'<details>', section_body))
        if count == 0:
            print("  [SKIP] 個別発言エントリなし")
            return 0

        # コメントブロックを抽出して除外（外側に出す）
        comment = ""
        comment_match = re.search(r'(<!--.*?-->)', section_body, re.DOTALL)
        if comment_match:
            comment = comment_match.group(1) + "\n\n"
            section_body = section_body.replace(comment_match.group(0), "").strip()

        # 個別detailsのスタイルを更新
        section_body = update_inner_details_style(section_body)

        # 外側アコーディオンで包む
        wrapped = f"""{comment}<details style="margin:16px 0">
<summary style="cursor:pointer;font-size:18px;font-weight:500;padding:8px 0;border-bottom:2px solid #1a4fa0;list-style:none;display:flex;justify-content:space-between">
<span>発言・活動記録</span>
<span style="font-size:13px;color:#888;font-weight:400">{count}件 ▶ クリックで展開</span>
</summary>
<div style="padding-top:8px">

{section_body}

</div>
</details>"""

        # 元のセクションを置換（## ヘッダーは外側summaryに統合されたので不要）
        new_content = content[:match.start()] + wrapped + content[match.end():]

        # 余分な空行を整理
        new_content = re.sub(r'\n{3,}', '\n\n', new_content)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return count
    except Exception:
        traceback.print_exc()
        return 0


def run():
    """メイン処理"""
    try:
        print("=" * 60)
        print("発言セクション二重アコーディオン化 v2.0.0")
        print("=" * 60)

        success = 0
        total_entries = 0
        for name in TARGETS:
            print(f"\n[処理] {name}")
            md_path = find_md_file(name)
            if not md_path:
                print("  [SKIP] MDファイルなし")
                continue

            count = wrap_section(md_path)
            if count > 0:
                print(f"  [OK] 外側アコーディオン追加（内側{count}件）→ {os.path.basename(md_path)}")
                success += 1
                total_entries += count
            else:
                print("  [SKIP] 変換対象なし")

        print(f"\n[DONE] {success}名 / 内側{total_entries}件")
        print("=" * 60)

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    run()
