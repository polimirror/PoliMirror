"""
PoliMirror - 政治資金収支報告書 Claude API構造化解析
v1.0.0

OCR済みPDFからテキストを再抽出し、Claude API (haiku) で構造化データに変換する。
対象: data/donations/ 以下の 2023_ocr.json が存在する17対象
結果: data/donations/{対象名}/2023_structured.json
"""
import json
import os
import re
import time
import traceback
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")), ".env"))

import anthropic
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io

# === 定数 ===
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
TEMP_PDF_DIR = os.path.join(PROJECT_ROOT, "data", "temp_pdf")

MODEL = "claude-haiku-4-5-20251001"
OCR_DPI = 300
OCR_LANG = "jpn"
MAX_TEXT_LEN = 8000

# tesseract設定
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
os.environ["TESSDATA_PREFIX"] = r"C:\Users\deco3\tessdata"

SYSTEM_PROMPT = "政治資金収支報告書のOCRテキストから情報を抽出するアシスタントです。JSONのみ返してください。"

USER_PROMPT_TEMPLATE = """以下は政治資金収支報告書のOCRテキストです。
以下の情報を抽出してJSONで返してください：

{{
  "individual_donations": {{
    "total_amount": 金額(整数・円),
    "count": 件数(整数)
  }},
  "corporate_donations": [
    {{"name": "企業名", "amount": 金額, "date": "日付"}}
  ],
  "group_donations": [
    {{"name": "団体名", "amount": 金額, "date": "日付"}}
  ],
  "party_events": [
    {{"name": "パーティー名", "income": 収入額, "date": "日付"}}
  ],
  "total_income": 収入総額,
  "total_expense": 支出総額
}}

注意：
- OCRノイズ（丸数字①②③→1,2,3、改行混入、文字化け）を補正して読み取ってください
- 金額は円単位の整数で返してください
- 日付が読み取れない場合は null にしてください
- 該当データがない項目は空配列 [] や 0 を返してください

OCRテキスト（先頭{max_len}文字）:
{ocr_text}
"""


def extract_text_from_pdfs(target_name):
    """対象名に対応するPDFファイルからテキストを抽出する"""
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", target_name)
    # 単一PDFまたは連番PDF
    pdf_files = []
    single = os.path.join(TEMP_PDF_DIR, f"{safe_name}_2023.pdf")
    if os.path.exists(single):
        pdf_files.append(single)
    else:
        i = 1
        while True:
            numbered = os.path.join(TEMP_PDF_DIR, f"{safe_name}_2023_{i:02d}.pdf")
            if os.path.exists(numbered):
                pdf_files.append(numbered)
                i += 1
            else:
                break

    if not pdf_files:
        print(f"  [WARN] PDFファイルなし: {safe_name}")
        return ""

    full_text = ""
    for pdf_idx, pdf_path in enumerate(pdf_files):
        try:
            doc = fitz.open(pdf_path)
            page_count = len(doc)
            print(f"    PDF {pdf_idx+1}/{len(pdf_files)}: {page_count}p ({os.path.basename(pdf_path)})")
            for pi, page in enumerate(doc):
                # テキスト埋め込み試行
                text = page.get_text().strip()
                if len(text) > 20:
                    full_text += text + "\n"
                else:
                    # OCR
                    pix = page.get_pixmap(dpi=OCR_DPI)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    text = pytesseract.image_to_string(img, lang=OCR_LANG)
                    full_text += text + "\n"

                if (pi + 1) % 20 == 0:
                    print(f"      {pi+1}/{page_count}p完了")

                # セクション検索用: 最初のPDFで十分なテキスト(50000文字)が集まり、
                # かつキーワードが見つかっていれば次のPDFに行かず早期終了
                if len(full_text) > 50000 and pdf_idx == 0:
                    for kw in SECTION_KEYWORDS:
                        if kw in full_text:
                            print(f"      -> 「{kw}」発見、残りページスキップ")
                            doc.close()
                            return full_text
            doc.close()
        except Exception:
            traceback.print_exc()

        # 最初のPDFで十分なテキストがあれば残りのPDFはスキップ
        if len(full_text) > 100000 and pdf_idx == 0 and len(pdf_files) > 1:
            has_kw = any(kw in full_text for kw in SECTION_KEYWORDS)
            if has_kw:
                print(f"    -> キーワード発見済み、残り{len(pdf_files)-1}PDFスキップ")
                break

    return full_text


# 収支データが含まれるセクションを検索するキーワード（優先順）
SECTION_KEYWORDS = ["収支の総括表", "収入の部", "寄附", "政治資金パーティー"]


def find_relevant_section(full_text, max_len=MAX_TEXT_LEN):
    """OCRテキストから収支データが含まれるセクションを検索し、
    そこを中心に max_len 文字を抽出する。
    見つからなければ先頭 max_len 文字を返す。"""
    for keyword in SECTION_KEYWORDS:
        pos = full_text.find(keyword)
        if pos >= 0:
            # キーワード位置の500文字前から抽出（前置きも含める）
            start = max(0, pos - 500)
            end = min(len(full_text), start + max_len)
            section = full_text[start:end]
            print(f"  セクション検索: 「{keyword}」を位置{pos:,}で発見 → {start:,}〜{end:,}")
            return section

    print(f"  セクション検索: キーワード未発見 → 先頭{max_len}文字を使用")
    return full_text[:max_len]


def analyze_with_claude(ocr_text, client):
    """Claude APIでOCRテキストを構造化解析する"""
    try:
        prompt = USER_PROMPT_TEMPLATE.format(
            max_len=len(ocr_text),
            ocr_text=ocr_text,
        )

        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        # JSON部分を抽出（コードブロックやAPIの余分なテキストを除去）
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if not json_match:
            print(f"  [ERROR] JSONが見つかりません")
            return None, 0, 0
        raw = json_match.group(0)

        result = json.loads(raw)

        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        print(f"  API: {tokens_in}入力 + {tokens_out}出力トークン")

        return result, tokens_in, tokens_out
    except json.JSONDecodeError as e:
        print(f"  [ERROR] JSON解析失敗: {e}")
        print(f"  Raw: {raw[:200]}")
        return None, 0, 0
    except Exception:
        traceback.print_exc()
        return None, 0, 0


def process_target(target_dir, client, force=False):
    """1対象を処理する"""
    target_name = os.path.basename(target_dir)
    ocr_path = os.path.join(target_dir, "2023_ocr.json")
    out_path = os.path.join(target_dir, "2023_structured.json")

    if not os.path.exists(ocr_path):
        return None

    # 既存の structured があればスキップ（force時は除く）
    if not force and os.path.exists(out_path):
        print(f"  [SKIP] 既存: {target_name}")
        with open(out_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # OCRメタ情報読み込み
    with open(ocr_path, "r", encoding="utf-8") as f:
        ocr_meta = json.load(f)

    print(f"\n[{target_name}] テキスト抽出中（全PDF）...")
    ocr_text = extract_text_from_pdfs(target_name)
    if not ocr_text:
        print(f"  [SKIP] テキスト抽出失敗")
        return None

    print(f"  テキスト: {len(ocr_text):,}文字")

    # OCRノイズ前処理: 丸数字→通常数字
    circle_map = {
        "⓪": "0", "①": "1", "②": "2", "③": "3", "④": "4",
        "⑤": "5", "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9",
        "⑩": "10", "⑪": "11", "⑫": "12", "⑬": "13", "⑭": "14",
        "⑮": "15", "⑯": "16", "⑰": "17", "⑱": "18", "⑲": "19",
        "⑳": "20",
    }
    for circle, num in circle_map.items():
        ocr_text = ocr_text.replace(circle, num)

    section = find_relevant_section(ocr_text)
    print(f"  API送信: {len(section):,}文字")

    result, tokens_in, tokens_out = analyze_with_claude(section, client)
    if not result:
        return None

    # 保存
    output = {
        "name": target_name,
        "type": ocr_meta.get("type", "unknown"),
        "year": "2023",
        "source": "総務省政治資金収支報告書",
        "analysis_model": MODEL,
        "analyzed_at": datetime.now().isoformat(),
        "ocr_text_length": len(ocr_text),
        "api_text_sent": min(len(ocr_text), MAX_TEXT_LEN),
        "tokens": {"input": tokens_in, "output": tokens_out},
        "data": result,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  -> {out_path}")
    return output


def print_summary(results):
    """結果サマリーを出力"""
    print("\n" + "=" * 60)
    print("構造化解析 結果サマリー")
    print("=" * 60)

    # 1. 林芳正の企業献金TOP5
    hayashi = next((r for r in results if r and r["name"] == "林芳正"), None)
    if hayashi and hayashi["data"].get("corporate_donations"):
        corps = sorted(
            hayashi["data"]["corporate_donations"],
            key=lambda x: x.get("amount", 0) or 0,
            reverse=True,
        )
        print("\n【林芳正 企業献金TOP5】")
        for i, c in enumerate(corps[:5], 1):
            amt = c.get("amount", 0) or 0
            print(f"  {i}. {c.get('name', '不明')}: {amt:,}円")

    # 2. 自由民主党の収入・企業献金
    ldp = next((r for r in results if r and r["name"] == "自由民主党"), None)
    if ldp:
        d = ldp["data"]
        print(f"\n【自由民主党】")
        print(f"  収入総額: {d.get('total_income', 0) or 0:,}円")
        print(f"  支出総額: {d.get('total_expense', 0) or 0:,}円")
        corp_total = sum((c.get("amount", 0) or 0) for c in d.get("corporate_donations", []))
        print(f"  企業献金合計: {corp_total:,}円 ({len(d.get('corporate_donations', []))}件)")

    # 3. 各政党の個人献金比率
    parties = [r for r in results if r and r.get("type") == "party"]
    if parties:
        print("\n【各政党 個人献金比率】")
        for p in parties:
            d = p["data"]
            total_income = d.get("total_income", 0) or 0
            ind_amount = 0
            ind_data = d.get("individual_donations", {})
            if isinstance(ind_data, dict):
                ind_amount = ind_data.get("total_amount", 0) or 0
            ratio = (ind_amount / total_income * 100) if total_income > 0 else 0
            print(f"  {p['name']}: 個人{ind_amount:,}円 / 収入{total_income:,}円 ({ratio:.1f}%)")


if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("PoliMirror - 政治資金 Claude API構造化解析 v1.1.0")
    print(f"モデル: {MODEL}")
    print(f"テキスト上限: {MAX_TEXT_LEN}文字/対象")
    print("=" * 60)

    client = anthropic.Anthropic()

    # --reprocess NAME1,NAME2: 指定対象のみ強制再処理
    reprocess_names = None
    for arg in sys.argv[1:]:
        if arg.startswith("--reprocess="):
            reprocess_names = arg.split("=", 1)[1].split(",")

    # 対象ディレクトリ一覧
    targets = []
    for d in sorted(os.listdir(DONATIONS_DIR)):
        full = os.path.join(DONATIONS_DIR, d)
        if os.path.isdir(full) and os.path.exists(os.path.join(full, "2023_ocr.json")):
            if reprocess_names is None or d in reprocess_names:
                targets.append(full)

    force = reprocess_names is not None
    print(f"\n対象: {len(targets)}件 {'(強制再処理)' if force else ''}")
    for t in targets:
        print(f"  - {os.path.basename(t)}")

    # 処理実行
    results = []
    total_tokens_in = 0
    total_tokens_out = 0
    success = 0
    fail = 0

    for i, target_dir in enumerate(targets, 1):
        name = os.path.basename(target_dir)
        print(f"\n--- [{i}/{len(targets)}] {name} ---")
        try:
            result = process_target(target_dir, client, force=force)
            if result:
                results.append(result)
                t = result.get("tokens", {})
                total_tokens_in += t.get("input", 0)
                total_tokens_out += t.get("output", 0)
                success += 1
            else:
                fail += 1
        except Exception:
            traceback.print_exc()
            fail += 1

    print(f"\n[INFO] 完了: 成功{success}, 失敗{fail}")
    print(f"[INFO] API使用量: {total_tokens_in:,}入力 + {total_tokens_out:,}出力トークン")

    # コスト概算 (haiku: $0.80/1M入力, $4/1M出力)
    cost_in = total_tokens_in / 1_000_000 * 0.80
    cost_out = total_tokens_out / 1_000_000 * 4.00
    print(f"[INFO] 概算コスト: ${cost_in + cost_out:.4f}")

    # サマリー表示
    print_summary(results)

    # サマリーJSON保存
    summary_path = os.path.join(DONATIONS_DIR, "structured_summary_2023.json")
    summary = {
        "analyzed_at": datetime.now().isoformat(),
        "model": MODEL,
        "total_targets": len(targets),
        "success": success,
        "fail": fail,
        "total_tokens": {"input": total_tokens_in, "output": total_tokens_out},
        "results": [
            {
                "name": r["name"],
                "type": r.get("type"),
                "total_income": r["data"].get("total_income", 0),
                "total_expense": r["data"].get("total_expense", 0),
                "corporate_count": len(r["data"].get("corporate_donations", [])),
                "group_count": len(r["data"].get("group_donations", [])),
                "event_count": len(r["data"].get("party_events", [])),
            }
            for r in results
        ],
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n[INFO] サマリー保存: {summary_path}")
