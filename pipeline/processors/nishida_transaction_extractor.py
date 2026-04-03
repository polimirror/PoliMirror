"""
PoliMirror - 西田昌司 全トランザクション抽出
v1.0.0

4団体×2年=8PDFから全収入・支出トランザクションを抽出する。
Claude API (haiku) で OCRテキストを構造化。

出力:
  data/donations/西田昌司/2022_transactions.json
  data/donations/西田昌司/2023_transactions.json
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
OUTPUT_DIR = os.path.join(DONATIONS_DIR, "西田昌司")

MODEL = "claude-haiku-4-5-20251001"
OCR_DPI = 300
OCR_LANG = "jpn"
API_TIMEOUT = 180  # 1PDF=180秒

# 団体名→PDF URLのマッピング（pref_index + 手動取得分）
SOURCE_URLS = {
    "西田会": {
        "2022": "https://www.pref.kyoto.jp/senkan/r5teikikouhyou/documents/4-k3552.pdf",
        "2023": "https://www.pref.kyoto.jp/senkan/r6teikikouhyou/documents/5-k-3521.pdf",
    },
    "一粒会": {
        "2022": "https://www.pref.kyoto.jp/senkan/r5teikikouhyou/documents/4-k-2014-re060131.pdf",
        "2023": "https://www.pref.kyoto.jp/senkan/r6teikikouhyou/documents/5-k-2016.pdf",
    },
    "京都医療政策フォーラム": {
        "2022": "https://www.pref.kyoto.jp/senkan/r5teikikouhyou/documents/4-k3214.pdf",
        "2023": "https://www.pref.kyoto.jp/senkan/r6teikikouhyou/documents/5-k-3202.pdf",
    },
    "自由民主党京都府参議院選挙区第四支部": {
        "2022": "https://www.pref.kyoto.jp/senkan/r5teikikouhyou/documents/4-1083.pdf",
        "2023": "https://www.pref.kyoto.jp/senkan/r6teikikouhyou/documents/5-1084.pdf",
    },
}

# tesseract設定
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
os.environ["TESSDATA_PREFIX"] = r"C:\Users\deco3\tessdata"

# 対象団体
ORGANIZATIONS = [
    "西田会",
    "一粒会",
    "京都医療政策フォーラム",
    "自由民主党京都府参議院選挙区第四支部",
]

SYSTEM_PROMPT = "政治資金収支報告書のOCRテキストから全トランザクションを抽出するアシスタントです。JSONのみ返してください。"

USER_PROMPT_TEMPLATE = """以下は政治資金収支報告書のOCRテキストです。
収入・支出の全トランザクションを1行ずつ抽出し、
JSONの配列で返してください。

抽出する項目：
- record_type: "収入" or "支出"
- summary1: 摘要1（収入・支出の種別）
- summary2: 摘要2（相手方名・具体的内容）
- amount: 金額（数値のみ・円単位）
- date: 日付（YYYY/MM/DD形式・年のみの場合はYYYY）
- organization: 政治団体名（どの団体の報告書か）

ルール：
- 金額が読み取れない行はスキップ
- 合計・小計行は record_type: "合計" として含める
- JSONのみ返す・余分なテキスト不要

OCRテキスト（団体: {org_name}）:
{ocr_text}
"""


def extract_text_from_pdf(pdf_path):
    """PDFからテキストを全ページ抽出する（上限なし）"""
    try:
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        print(f"    ページ数: {page_count}")
        full_text = ""

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

            if (pi + 1) % 10 == 0:
                print(f"      {pi+1}/{page_count}p完了")

        doc.close()

        # OCRノイズ前処理: 丸数字→通常数字
        circle_map = {
            "⓪": "0", "①": "1", "②": "2", "③": "3", "④": "4",
            "⑤": "5", "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9",
            "⑩": "10", "⑪": "11", "⑫": "12", "⑬": "13", "⑭": "14",
            "⑮": "15", "⑯": "16", "⑰": "17", "⑱": "18", "⑲": "19",
            "⑳": "20",
        }
        for circle, num in circle_map.items():
            full_text = full_text.replace(circle, num)

        return full_text
    except Exception:
        traceback.print_exc()
        return ""


def analyze_chunk_with_claude(ocr_text, org_name, client, chunk_idx=0, total_chunks=1):
    """Claude APIでOCRテキストチャンクを構造化解析する"""
    try:
        prompt = USER_PROMPT_TEMPLATE.format(
            org_name=org_name,
            ocr_text=ocr_text,
        )

        print(f"    API送信 (チャンク{chunk_idx+1}/{total_chunks}): {len(ocr_text):,}文字")

        response = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            timeout=API_TIMEOUT,
        )

        raw = response.content[0].text.strip()

        # JSON配列を抽出
        json_match = re.search(r"\[[\s\S]*\]", raw)
        if not json_match:
            # オブジェクトの場合も試す
            json_match = re.search(r"\{[\s\S]*\}", raw)
            if json_match:
                result = json.loads(json_match.group(0))
                if not isinstance(result, list):
                    result = [result]
            else:
                print(f"    [ERROR] JSONが見つかりません")
                print(f"    Raw: {raw[:300]}")
                return [], 0, 0
        else:
            result = json.loads(json_match.group(0))

        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        print(f"    API: {tokens_in}入力 + {tokens_out}出力トークン → {len(result)}件抽出")

        return result, tokens_in, tokens_out
    except json.JSONDecodeError as e:
        print(f"    [ERROR] JSON解析失敗: {e}")
        print(f"    Raw: {raw[:300]}")
        return [], 0, 0
    except Exception:
        traceback.print_exc()
        return [], 0, 0


def process_pdf(pdf_path, org_name, client, source_url=None):
    """1つのPDFを処理して全トランザクションを返す"""
    print(f"\n  [{org_name}] {os.path.basename(pdf_path)}")

    # テキスト抽出
    full_text = extract_text_from_pdf(pdf_path)
    if not full_text:
        print(f"    [SKIP] テキスト抽出失敗")
        return [], 0, 0

    print(f"    テキスト: {len(full_text):,}文字")

    # テキストをチャンク分割（haiku の入力上限を考慮して1チャンク15000文字）
    CHUNK_SIZE = 15000
    CHUNK_OVERLAP = 500
    all_transactions = []
    total_in = 0
    total_out = 0

    if len(full_text) <= CHUNK_SIZE:
        chunks = [full_text]
    else:
        chunks = []
        pos = 0
        while pos < len(full_text):
            end = min(pos + CHUNK_SIZE, len(full_text))
            chunks.append(full_text[pos:end])
            pos = end - CHUNK_OVERLAP
            if pos + CHUNK_OVERLAP >= len(full_text):
                break

    print(f"    チャンク数: {len(chunks)}")

    for ci, chunk in enumerate(chunks):
        transactions, t_in, t_out = analyze_chunk_with_claude(
            chunk, org_name, client, ci, len(chunks)
        )
        all_transactions.extend(transactions)
        total_in += t_in
        total_out += t_out
        # API rate limit
        if ci < len(chunks) - 1:
            time.sleep(2)

    # source_urlを全トランザクションに埋め込む
    if source_url:
        for t in all_transactions:
            t["source_url"] = source_url

    return all_transactions, total_in, total_out


def deduplicate_transactions(transactions):
    """重複トランザクションを除去する（チャンクオーバーラップ由来）"""
    seen = set()
    unique = []
    for t in transactions:
        key = (
            t.get("record_type", ""),
            t.get("summary1", ""),
            t.get("summary2", ""),
            t.get("amount", 0),
            t.get("date", ""),
            t.get("organization", ""),
        )
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


def generate_summary(transactions_2022, transactions_2023):
    """トランザクションから集計サマリーを生成する"""
    def summarize_year(transactions):
        income = [t for t in transactions if t.get("record_type") == "収入"]
        expense = [t for t in transactions if t.get("record_type") == "支出"]

        total_income = sum(t.get("amount", 0) or 0 for t in income)
        total_expense = sum(t.get("amount", 0) or 0 for t in expense)

        # 収入の種別集計
        income_by_type = {}
        for t in income:
            s1 = t.get("summary1", "不明") or "不明"
            income_by_type[s1] = income_by_type.get(s1, 0) + (t.get("amount", 0) or 0)

        # 支出の種別集計
        expense_by_type = {}
        for t in expense:
            s1 = t.get("summary1", "不明") or "不明"
            expense_by_type[s1] = expense_by_type.get(s1, 0) + (t.get("amount", 0) or 0)

        # 寄付ランキング（収入で summary2 がある企業・団体）
        donors = {}
        for t in income:
            s2 = t.get("summary2", "") or ""
            if s2 and s2 != "不明":
                donors[s2] = donors.get(s2, 0) + (t.get("amount", 0) or 0)
        donor_ranking = sorted(donors.items(), key=lambda x: x[1], reverse=True)

        return {
            "total_income": total_income,
            "total_expense": total_expense,
            "income_count": len(income),
            "expense_count": len(expense),
            "income_by_type": dict(sorted(income_by_type.items(), key=lambda x: x[1], reverse=True)),
            "expense_by_type": dict(sorted(expense_by_type.items(), key=lambda x: x[1], reverse=True)),
            "donor_ranking": [{"name": name, "amount": amt} for name, amt in donor_ranking],
        }

    summary = {
        "politician": "西田昌司",
        "organizations": ORGANIZATIONS,
        "generated_at": datetime.now().isoformat(),
        "2022": summarize_year(transactions_2022),
        "2023": summarize_year(transactions_2023),
    }

    return summary


if __name__ == "__main__":
    print("=" * 60)
    print("西田昌司 全トランザクション抽出 v1.0.0")
    print(f"モデル: {MODEL}")
    print(f"対象団体: {len(ORGANIZATIONS)}団体 × 2年 = 8PDF")
    print("=" * 60)

    client = anthropic.Anthropic()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    grand_total_in = 0
    grand_total_out = 0

    for year in ["2022", "2023"]:
        print(f"\n{'='*40}")
        print(f"  {year}年 処理開始")
        print(f"{'='*40}")

        year_transactions = []
        year_success = 0
        year_fail = 0

        for org in ORGANIZATIONS:
            pdf_name = f"西田昌司_{org}_{year}.pdf"
            pdf_path = os.path.join(TEMP_PDF_DIR, pdf_name)

            if not os.path.exists(pdf_path):
                print(f"\n  [WARN] PDFなし: {pdf_name}")
                year_fail += 1
                continue

            try:
                source_url = SOURCE_URLS.get(org, {}).get(year)
                transactions, t_in, t_out = process_pdf(pdf_path, org, client, source_url=source_url)
                year_transactions.extend(transactions)
                grand_total_in += t_in
                grand_total_out += t_out
                year_success += 1
                print(f"    -> {len(transactions)}件抽出")
            except Exception:
                traceback.print_exc()
                year_fail += 1

            # API rate limit between PDFs
            time.sleep(3)

        # 重複除去
        before_dedup = len(year_transactions)
        year_transactions = deduplicate_transactions(year_transactions)
        after_dedup = len(year_transactions)
        if before_dedup != after_dedup:
            print(f"\n  重複除去: {before_dedup} -> {after_dedup}件")

        # 保存
        out_path = os.path.join(OUTPUT_DIR, f"{year}_transactions.json")
        output = {
            "politician": "西田昌司",
            "year": int(year),
            "organizations": ORGANIZATIONS,
            "source": "京都府選管 政治資金収支報告書",
            "extraction_model": MODEL,
            "extracted_at": datetime.now().isoformat(),
            "transaction_count": len(year_transactions),
            "transactions": year_transactions,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"\n  {year}年: {len(year_transactions)}件 (成功{year_success}/失敗{year_fail})")
        print(f"  -> {out_path}")

        # 5件未満チェック
        if len(year_transactions) < 5:
            print(f"  [WARNING] トランザクション5件未満 - OCR精度の問題の可能性")

    # サマリー生成
    print(f"\n{'='*40}")
    print("  サマリー生成")
    print(f"{'='*40}")

    # 再読み込み
    with open(os.path.join(OUTPUT_DIR, "2022_transactions.json"), encoding="utf-8") as f:
        data_2022 = json.load(f)
    with open(os.path.join(OUTPUT_DIR, "2023_transactions.json"), encoding="utf-8") as f:
        data_2023 = json.load(f)

    summary = generate_summary(data_2022["transactions"], data_2023["transactions"])
    summary_path = os.path.join(OUTPUT_DIR, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"  -> {summary_path}")

    # 最終サマリー
    print(f"\n{'='*60}")
    print(f"完了サマリー")
    print(f"{'='*60}")
    print(f"  2022年: {data_2022['transaction_count']}件")
    print(f"  2023年: {data_2023['transaction_count']}件")
    print(f"  合計: {data_2022['transaction_count'] + data_2023['transaction_count']}件")
    print(f"  API使用量: {grand_total_in:,}入力 + {grand_total_out:,}出力トークン")
    cost_in = grand_total_in / 1_000_000 * 0.80
    cost_out = grand_total_out / 1_000_000 * 4.00
    print(f"  概算コスト: ${cost_in + cost_out:.4f}")

    # 2023年サマリー表示
    s23 = summary["2023"]
    print(f"\n  【2023年 収入】")
    print(f"    総額: {s23['total_income']:,}円 ({s23['income_count']}件)")
    for typ, amt in list(s23["income_by_type"].items())[:5]:
        print(f"      {typ}: {amt:,}円")
    print(f"\n  【2023年 支出】")
    print(f"    総額: {s23['total_expense']:,}円 ({s23['expense_count']}件)")
    for typ, amt in list(s23["expense_by_type"].items())[:5]:
        print(f"      {typ}: {amt:,}円")
    print(f"\n  【2023年 寄付元TOP10】")
    for i, d in enumerate(s23["donor_ranking"][:10], 1):
        print(f"    {i}. {d['name']}: {d['amount']:,}円")
