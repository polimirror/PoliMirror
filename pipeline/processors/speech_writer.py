"""
PoliMirror - 発言データMarkdown書き戻し
v1.0.0

data/speeches/{議員名}/{年}/{speechID}.json の発言データを
該当議員のMarkdownファイル（quartz/content/politicians/）の
「発言・活動記録」セクションに書き戻す。
"""
import json
import os
import re
import traceback
from glob import glob

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPEECHES_DIR = os.path.join(PROJECT_ROOT, "data", "speeches")
POLITICIANS_DIR = os.path.join(PROJECT_ROOT, "quartz", "content", "politicians")


def _clean_speech_text(speech: str, max_chars: int = 200) -> str:
    """発言テキストの冒頭max_chars文字を抽出（敬称プレフィックス除去）"""
    try:
        text = speech.strip()
        # 「○安倍内閣総理大臣　」等のプレフィックスを除去
        text = re.sub(r"^○[^\s　]+[\s　]+", "", text)
        # 改行を半角スペースに
        text = text.replace("\r\n", " ").replace("\n", " ")
        # 連続空白を1つに
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_chars:
            return text[:max_chars] + "…"
        return text
    except Exception:
        traceback.print_exc()
        return speech[:max_chars] + "…" if len(speech) > max_chars else speech


def _find_md_file(name_no_space: str) -> str | None:
    """議員名（スペースなし）からMDファイルパスを探す"""
    try:
        # MDファイルは「石破 茂.md」のように姓名間にスペースがある
        # data/speechesは「石破茂」のようにスペースなし
        # 全MDファイルをスキャンしてスペース除去で一致するものを探す
        for md_path in glob(os.path.join(POLITICIANS_DIR, "**", "*.md"), recursive=True):
            basename = os.path.splitext(os.path.basename(md_path))[0]
            if basename == "index":
                continue
            # スペース除去して比較
            if basename.replace(" ", "").replace("　", "") == name_no_space:
                return md_path
        return None
    except Exception:
        traceback.print_exc()
        return None


def _load_speeches(name: str, limit: int = 10) -> list[dict]:
    """指定議員の発言を新しい順に最大limit件取得"""
    speeches = []
    try:
        speaker_dir = os.path.join(SPEECHES_DIR, name)
        if not os.path.isdir(speaker_dir):
            print(f"  [WARN] 発言ディレクトリなし: {speaker_dir}")
            return speeches

        for root, _dirs, files in os.walk(speaker_dir):
            for fname in files:
                if fname.endswith(".json") and "_analysis" not in fname:
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        speeches.append(data)
                    except Exception:
                        traceback.print_exc()

        # 日付の新しい順にソート
        speeches.sort(key=lambda x: x.get("date", ""), reverse=True)
        return speeches[:limit]

    except Exception:
        traceback.print_exc()
        return speeches


def _format_speech_entry(speech: dict) -> str:
    """発言1件をMarkdownエントリに変換"""
    try:
        date = speech.get("date", "不明")
        meeting = speech.get("nameOfMeeting", "不明")
        house = speech.get("nameOfHouse", "不明")
        session = speech.get("session", "?")
        speech_text = speech.get("speech", "")
        speech_url = speech.get("speechURL", "") or speech.get("meetingURL", "")

        summary = _clean_speech_text(speech_text)

        entry = f"### {date}｜{meeting}｜{house}｜信頼度★★★★★\n"
        entry += f"**発言要旨:** {summary}\n"
        if speech_url:
            entry += f"**出典:** [{meeting} 第{session}回国会]({speech_url})\n"
        else:
            entry += f"**出典:** {meeting} 第{session}回国会\n"

        return entry
    except Exception:
        traceback.print_exc()
        return ""


def write_speeches(name_ja: str, limit: int = 10) -> dict:
    """
    指定議員の発言をMDファイルに書き戻す。

    Args:
        name_ja: 議員名（スペースなし、例: "石破茂"）
        limit: 最大件数（デフォルト10）

    Returns:
        {"status": "ok"|"skipped"|"error", "count": int, "reason": str}
    """
    try:
        print(f"[INFO] {name_ja}: 処理開始")

        # 1. MDファイルを探す
        md_path = _find_md_file(name_ja)
        if not md_path:
            print(f"  [SKIP] MDファイルが見つかりません: {name_ja}")
            return {"status": "skipped", "count": 0, "reason": "MDファイルなし"}

        # 2. 発言データを読み込む
        speeches = _load_speeches(name_ja, limit)
        if not speeches:
            print(f"  [SKIP] 発言データが0件: {name_ja}")
            return {"status": "skipped", "count": 0, "reason": "発言0件"}

        # 3. Markdownエントリを生成
        entries = []
        for sp in speeches:
            entry = _format_speech_entry(sp)
            if entry:
                entries.append(entry)

        if not entries:
            print(f"  [SKIP] 有効な発言エントリなし: {name_ja}")
            return {"status": "skipped", "count": 0, "reason": "エントリ生成失敗"}

        speech_section = "\n".join(entries)

        # 4. MDファイルを読み込んで発言セクションを更新
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 「## 発言・活動記録」から「## 投票行動」の間を書き換え
        pattern = r"(## 発言・活動記録\n)(.*?)(## 投票行動)"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            print(f"  [WARN] 発言セクションが見つかりません: {md_path}")
            return {"status": "error", "count": 0, "reason": "セクション不在"}

        # コメントブロックは残す
        comment_match = re.search(r"(<!--.*?-->)", match.group(2), re.DOTALL)
        comment_block = comment_match.group(1) + "\n\n" if comment_match else ""

        new_section = f"{match.group(1)}\n{comment_block}{speech_section}\n\n{match.group(3)}"
        content = content[:match.start()] + new_section + content[match.end():]

        # 5. 書き戻し
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"  [OK] {name_ja}: {len(entries)}件の発言を書き込み → {os.path.basename(md_path)}")
        return {"status": "ok", "count": len(entries), "reason": ""}

    except Exception:
        traceback.print_exc()
        return {"status": "error", "count": 0, "reason": "例外発生"}


def write_all(limit: int = 10) -> dict:
    """
    発言データが存在する全議員に対してwrite_speechesを実行。

    Returns:
        {"total": int, "ok": int, "skipped": int, "error": int, "details": list}
    """
    stats = {"total": 0, "ok": 0, "skipped": 0, "error": 0, "details": []}
    try:
        # data/speeches/ 配下の全議員ディレクトリを取得
        if not os.path.isdir(SPEECHES_DIR):
            print(f"[ERROR] 発言ディレクトリが存在しません: {SPEECHES_DIR}")
            return stats

        speakers = sorted([
            d for d in os.listdir(SPEECHES_DIR)
            if os.path.isdir(os.path.join(SPEECHES_DIR, d))
        ])
        stats["total"] = len(speakers)
        print(f"[INFO] 全{len(speakers)}名の議員を処理")
        print("=" * 60)

        for i, name in enumerate(speakers, 1):
            print(f"\n[{i}/{len(speakers)}] {name}")
            result = write_speeches(name, limit=limit)
            result["name"] = name

            if result["status"] == "ok":
                stats["ok"] += 1
            elif result["status"] == "skipped":
                stats["skipped"] += 1
            else:
                stats["error"] += 1

            stats["details"].append(result)

        print("\n" + "=" * 60)
        print(f"[DONE] 完了: 成功={stats['ok']} スキップ={stats['skipped']} エラー={stats['error']} / 全{stats['total']}名")
        print("=" * 60)

        return stats

    except Exception:
        traceback.print_exc()
        return stats


def main():
    """テスト実行: 石破茂・野田佳彦の2名（安倍晋三はMDなし）"""
    try:
        print("=" * 60)
        print("PoliMirror Speech Writer v1.0.0")
        print("=" * 60)

        test_names = ["安倍晋三", "石破茂", "野田佳彦"]
        for name in test_names:
            result = write_speeches(name, limit=10)
            print(f"  結果: {result}")

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    main()
