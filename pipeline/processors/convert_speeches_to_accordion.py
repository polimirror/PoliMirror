"""
PoliMirror - 既存発言セクションをアコーディオン形式に一括変換 v1.0.0

既存の ### 日付｜委員会｜院 形式を <details><summary> 形式に変換する。
対象: TARGETS の10名
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


def convert_entry(match) -> str:
    """1件の発言エントリを変換"""
    try:
        title = match.group(1).strip()  # 2024-06-19｜国家基本政策委員会合同審査会｜両院
        body = match.group(2).strip()

        # 出典行（<small>）を抽出
        source_line = "出典：国会議事録検索システム（国立国会図書館）"
        small_match = re.search(r'<small>(.*?)</small>', body)
        if small_match:
            source_line = small_match.group(1)

        # 発言要旨を抽出
        summary = ""
        summary_match = re.search(r'\*\*発言要旨:\*\*\s*(.*?)(?=\n\*\*出典:|\Z)', body, re.DOTALL)
        if summary_match:
            summary = summary_match.group(1).strip()

        # 出典リンクを抽出
        link_match = re.search(r'\*\*出典:\*\*\s*\[([^\]]+)\]\(([^)]+)\)', body)
        plain_match = re.search(r'\*\*出典:\*\*\s*(.+)', body)
        if link_match:
            source_link = f'<a href="{link_match.group(2)}" target="_blank">{link_match.group(1)}</a>'
        elif plain_match:
            source_link = plain_match.group(1).strip()
        else:
            source_link = ""

        accordion = f'''<details>
<summary style="cursor:pointer;padding:8px 0;border-bottom:1px solid #e5e5e3;list-style:none;display:flex;justify-content:space-between;align-items:center">
<span style="font-size:14px;font-weight:500;color:#1a1a1a">{title}</span>
<span style="font-size:12px;color:#888">▶ 展開</span>
</summary>
<div style="padding:12px 0 16px;border-bottom:1px solid #f0f0ee">
{source_line}<br>
<strong>発言要旨:</strong> {summary}<br>
<strong>出典:</strong> {source_link}
</div>
</details>'''
        return accordion
    except Exception:
        traceback.print_exc()
        return match.group(0)


def convert_file(md_path, dry_run=False):
    """1ファイルの発言セクションを変換"""
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # ### タイトル + 続く行（次の ### か ## まで）をマッチ
        pattern = r'### ([\d\-]+｜[^\n]+)\n((?:(?!###\s|## ).+\n?)*)'
        matches = list(re.finditer(pattern, content))

        if not matches:
            print(f"  [SKIP] 発言エントリなし")
            return 0

        if dry_run:
            return len(matches)

        new_content = content
        # 後ろから置換（オフセットのズレ防止）
        for m in reversed(matches):
            replacement = convert_entry(m)
            new_content = new_content[:m.start()] + replacement + "\n\n" + new_content[m.end():]

        # 余分な空行を整理
        new_content = re.sub(r'\n{3,}', '\n\n', new_content)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return len(matches)
    except Exception:
        traceback.print_exc()
        return 0


def run():
    """メイン処理"""
    try:
        print("=" * 60)
        print("発言アコーディオン変換 v1.0.0")
        print("=" * 60)

        # Phase 1: サンプル3件を表示
        print("\n[Phase 1] サンプル確認（最初の3件）")
        print("-" * 60)

        sample_path = find_md_file("石破茂")
        if sample_path:
            with open(sample_path, "r", encoding="utf-8") as f:
                content = f.read()
            pattern = r'### ([\d\-]+｜[^\n]+)\n((?:(?!###\s|## ).+\n?)*)'
            matches = list(re.finditer(pattern, content))
            for i, m in enumerate(matches[:3]):
                print(f"\n--- サンプル {i+1} ---")
                print("[変換前]")
                print(m.group(0).strip())
                print("\n[変換後]")
                print(convert_entry(m))
                print()

        # Phase 2: 全10名を変換
        print("\n[Phase 2] 全10名を変換")
        print("-" * 60)

        success = 0
        total_entries = 0
        for name in TARGETS:
            print(f"\n[処理] {name}")
            md_path = find_md_file(name)
            if not md_path:
                print("  [SKIP] MDファイルなし")
                continue

            count = convert_file(md_path)
            if count > 0:
                print(f"  [OK] {count}件変換 → {os.path.basename(md_path)}")
                success += 1
                total_entries += count
            else:
                print("  [SKIP] 変換対象なし")

        print(f"\n[DONE] {success}名 / {total_entries}件変換")
        print("=" * 60)

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    run()
