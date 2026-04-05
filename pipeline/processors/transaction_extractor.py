"""
PoliMirror - 汎用トランザクション抽出
v1.0.0

任意の議員のPDFから全収入・支出トランザクションを抽出する。
Claude API (haiku) で OCRテキストを構造化。

使用法:
  python transaction_extractor.py 稲田朋美
  python transaction_extractor.py 稲田朋美 --year 2023
  python transaction_extractor.py --batch 10        # 先頭10名バッチ
  python transaction_extractor.py --batch 0         # 全員
  python transaction_extractor.py --batch 10 --resume  # 未処理のみ

出力:
  data/donations/{議員名}/{year}_transactions.json
  data/donations/{議員名}/summary.json
"""
import argparse
import json
import os
import re
import sys
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
TEMP_PDF_DIR = os.path.join(PROJECT_ROOT, "data", "temp_pdf", "pref")
BATCH_RESULT_DIR = os.path.join(PROJECT_ROOT, "data", "batch_results")

MODEL = "claude-haiku-4-5-20251001"
OCR_DPI = 300
OCR_LANG = "jpn"
API_TIMEOUT = 180

# tesseract設定
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
os.environ["TESSDATA_PREFIX"] = r"C:\Users\deco3\tessdata"

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

# 丸数字→通常数字マッピング
CIRCLE_MAP = {
    "⓪": "0", "①": "1", "②": "2", "③": "3", "④": "4",
    "⑤": "5", "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9",
    "⑩": "10", "⑪": "11", "⑫": "12", "⑬": "13", "⑭": "14",
    "⑮": "15", "⑯": "16", "⑰": "17", "⑱": "18", "⑲": "19",
    "⑳": "20",
}


def scan_politician_pdfs(politician_name):
    """指定議員のPDFファイルを検出し、(org, year, filepath) のリストを返す"""
    results = []
    if not os.path.isdir(TEMP_PDF_DIR):
        print(f"  [ERROR] PDFディレクトリなし: {TEMP_PDF_DIR}")
        return results

    for fname in os.listdir(TEMP_PDF_DIR):
        if not fname.endswith(".pdf"):
            continue
        # test_ プレフィクス除去
        clean = fname
        if clean.startswith("test_"):
            clean = clean[5:]
        # パターン: {politician}_{org}_{year}.pdf
        m = re.match(r'^(.+?)_(.+)_(2022|2023)\.pdf$', clean)
        if not m:
            continue
        pol, org, year = m.groups()
        if pol == politician_name:
            results.append({
                "org": org,
                "year": year,
                "filepath": os.path.join(TEMP_PDF_DIR, fname),
            })

    # 年→団体名でソート
    results.sort(key=lambda x: (x["year"], x["org"]))
    return results


def load_pref_index_url(org_name, year):
    """pref_indexファイルからsource_urlを検索する"""
    try:
        for fname in os.listdir(DONATIONS_DIR):
            if not fname.startswith("pref_index_") or not fname.endswith(f"_{year}.json"):
                continue
            fpath = os.path.join(DONATIONS_DIR, fname)
            with open(fpath, encoding="utf-8") as f:
                index = json.load(f)
            # 完全一致
            if org_name in index:
                return index[org_name]
            # 括弧等を除去して部分一致
            org_clean = re.sub(r'[（(].+$', '', org_name).strip()
            for key, url in index.items():
                key_clean = re.sub(r'[（(].+$', '', key).strip()
                if org_clean == key_clean:
                    return url
    except Exception:
        traceback.print_exc()
    return None


def extract_text_from_pdf(pdf_path):
    """PDFからテキストを全ページ抽出する"""
    try:
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        print(f"    ページ数: {page_count}")
        full_text = ""

        for pi, page in enumerate(doc):
            text = page.get_text().strip()
            if len(text) > 20:
                full_text += text + "\n"
            else:
                pix = page.get_pixmap(dpi=OCR_DPI)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img, lang=OCR_LANG)
                full_text += text + "\n"

            if (pi + 1) % 10 == 0:
                print(f"      {pi+1}/{page_count}p完了")

        doc.close()

        for circle, num in CIRCLE_MAP.items():
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

        json_match = re.search(r"\[[\s\S]*\]", raw)
        if not json_match:
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
        print(f"    API: {tokens_in}入力 + {tokens_out}出力トークン -> {len(result)}件抽出")

        return result, tokens_in, tokens_out
    except json.JSONDecodeError as e:
        print(f"    [ERROR] JSON解析失敗: {e}")
        return [], 0, 0
    except Exception:
        traceback.print_exc()
        return [], 0, 0


def process_pdf(pdf_path, org_name, client, source_url=None):
    """1つのPDFを処理して全トランザクションを返す"""
    print(f"\n  [{org_name}] {os.path.basename(pdf_path)}")

    full_text = extract_text_from_pdf(pdf_path)
    if not full_text:
        print(f"    [SKIP] テキスト抽出失敗")
        return [], 0, 0

    print(f"    テキスト: {len(full_text):,}文字")

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
        if ci < len(chunks) - 1:
            time.sleep(2)

    if source_url:
        for t in all_transactions:
            t["source_url"] = source_url

    return all_transactions, total_in, total_out


def deduplicate_transactions(transactions):
    """重複トランザクションを除去する"""
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


def generate_summary(politician_name, transactions_by_year, organizations):
    """トランザクションから集計サマリーを生成する"""
    def summarize_year(transactions):
        income = [t for t in transactions if t.get("record_type") == "収入"]
        expense = [t for t in transactions if t.get("record_type") == "支出"]

        total_income = sum(t.get("amount", 0) or 0 for t in income)
        total_expense = sum(t.get("amount", 0) or 0 for t in expense)

        income_by_type = {}
        for t in income:
            s1 = t.get("summary1", "不明") or "不明"
            income_by_type[s1] = income_by_type.get(s1, 0) + (t.get("amount", 0) or 0)

        expense_by_type = {}
        for t in expense:
            s1 = t.get("summary1", "不明") or "不明"
            expense_by_type[s1] = expense_by_type.get(s1, 0) + (t.get("amount", 0) or 0)

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
        "politician": politician_name,
        "organizations": organizations,
        "generated_at": datetime.now().isoformat(),
    }

    for year, transactions in sorted(transactions_by_year.items()):
        summary[year] = summarize_year(transactions)

    return summary


def extract_politician(politician_name, client):
    """1議員分の全トランザクション抽出を実行する"""
    pdfs = scan_politician_pdfs(politician_name)
    if not pdfs:
        print(f"  [SKIP] PDFなし: {politician_name}")
        return None

    output_dir = os.path.join(DONATIONS_DIR, politician_name)
    os.makedirs(output_dir, exist_ok=True)

    print(f"  PDF: {len(pdfs)}件")
    for p in pdfs:
        print(f"    {p['year']} {p['org']}")

    grand_total_in = 0
    grand_total_out = 0
    transactions_by_year = {}
    all_orgs = set()

    for pdf_info in pdfs:
        org = pdf_info["org"]
        year = pdf_info["year"]
        filepath = pdf_info["filepath"]
        all_orgs.add(org)

        source_url = load_pref_index_url(org, year)
        if source_url:
            print(f"    source_url: {source_url[:60]}...")

        try:
            transactions, t_in, t_out = process_pdf(filepath, org, client, source_url=source_url)
            if year not in transactions_by_year:
                transactions_by_year[year] = []
            transactions_by_year[year].extend(transactions)
            grand_total_in += t_in
            grand_total_out += t_out
            print(f"    -> {len(transactions)}件抽出")
        except Exception:
            traceback.print_exc()

        time.sleep(3)

    # 年ごとに重複除去・保存
    total_count = 0
    for year in sorted(transactions_by_year.keys()):
        before = len(transactions_by_year[year])
        transactions_by_year[year] = deduplicate_transactions(transactions_by_year[year])
        after = len(transactions_by_year[year])
        if before != after:
            print(f"  {year}年 重複除去: {before} -> {after}件")

        out_path = os.path.join(output_dir, f"{year}_transactions.json")
        output = {
            "politician": politician_name,
            "year": int(year),
            "organizations": sorted(all_orgs),
            "source": "都道府県選管 政治資金収支報告書",
            "extraction_model": MODEL,
            "extracted_at": datetime.now().isoformat(),
            "transaction_count": after,
            "transactions": transactions_by_year[year],
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"  -> {out_path} ({after}件)")
        total_count += after

    # サマリー生成
    summary = generate_summary(politician_name, transactions_by_year, sorted(all_orgs))
    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  -> {summary_path}")

    return {
        "politician": politician_name,
        "pdfs": len(pdfs),
        "total_transactions": total_count,
        "years": sorted(transactions_by_year.keys()),
        "tokens_in": grand_total_in,
        "tokens_out": grand_total_out,
    }


def list_all_politicians_with_pdfs():
    """PDFが存在する全議員名のリストを返す"""
    politicians = set()
    if not os.path.isdir(TEMP_PDF_DIR):
        return []
    for fname in os.listdir(TEMP_PDF_DIR):
        if not fname.endswith(".pdf"):
            continue
        clean = fname
        if clean.startswith("test_"):
            clean = clean[5:]
        m = re.match(r'^(.+?)_(.+)_(2022|2023)\.pdf$', clean)
        if m:
            politicians.add(m.group(1))
    return sorted(politicians)


def run_batch(limit=None, resume=False):
    """バッチ実行"""
    start_time = time.time()
    os.makedirs(BATCH_RESULT_DIR, exist_ok=True)

    all_politicians = list_all_politicians_with_pdfs()

    if resume:
        already_done = set()
        for name in all_politicians:
            # summary.json が存在 = 抽出済み
            spath = os.path.join(DONATIONS_DIR, name, "summary.json")
            if os.path.exists(spath):
                already_done.add(name)
        print(f"  処理済みスキップ: {len(already_done)}名")
        all_politicians = [p for p in all_politicians if p not in already_done]

    targets = all_politicians if (limit is None or limit == 0) else all_politicians[:limit]

    print("=" * 60)
    print(f"PoliMirror - トランザクション抽出バッチ v1.0.0")
    print(f"対象議員: {len(targets)}名 (全候補: {len(all_politicians)}名)")
    print(f"モデル: {MODEL}")
    print(f"モード: {'テスト' if limit else '全件'}{' (resume)' if resume else ''}")
    print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    client = anthropic.Anthropic()

    results = {
        "started_at": datetime.now().isoformat(),
        "mode": f"test_{limit}" if limit else "full",
        "model": MODEL,
        "total_targets": len(targets),
        "completed": 0,
        "skipped": 0,
        "errors": 0,
        "total_transactions": 0,
        "total_tokens_in": 0,
        "total_tokens_out": 0,
        "details": [],
    }

    for i, name in enumerate(targets):
        idx = f"[{i+1}/{len(targets)}]"
        print(f"\n{'='*40}")
        print(f"{idx} {name}")
        print(f"{'='*40}")

        try:
            result = extract_politician(name, client)
            if result is None:
                results["skipped"] += 1
                results["details"].append({"politician": name, "status": "skipped"})
            else:
                results["completed"] += 1
                results["total_transactions"] += result["total_transactions"]
                results["total_tokens_in"] += result["tokens_in"]
                results["total_tokens_out"] += result["tokens_out"]
                results["details"].append({
                    "politician": name,
                    "status": "ok",
                    "transactions": result["total_transactions"],
                    "pdfs": result["pdfs"],
                    "years": result["years"],
                })
        except Exception as e:
            traceback.print_exc()
            results["errors"] += 1
            results["details"].append({
                "politician": name,
                "status": "error",
                "error": str(e),
            })

        # 中間保存（5件ごと）
        if (i + 1) % 5 == 0:
            results["last_saved"] = datetime.now().isoformat()
            with open(os.path.join(BATCH_RESULT_DIR, "transaction_batch.json"), "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

    # 最終保存
    elapsed = time.time() - start_time
    results["finished_at"] = datetime.now().isoformat()
    results["elapsed_seconds"] = round(elapsed, 1)

    result_path = os.path.join(BATCH_RESULT_DIR, "transaction_batch.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # サマリー
    print("\n" + "=" * 60)
    print("バッチ完了サマリー")
    print("=" * 60)
    print(f"  対象: {len(targets)}名")
    print(f"  完了: {results['completed']}名")
    print(f"  スキップ: {results['skipped']}名")
    print(f"  エラー: {results['errors']}名")
    print(f"  総トランザクション: {results['total_transactions']}件")
    print(f"  API: {results['total_tokens_in']:,}入力 + {results['total_tokens_out']:,}出力トークン")
    cost_in = results['total_tokens_in'] / 1_000_000 * 0.80
    cost_out = results['total_tokens_out'] / 1_000_000 * 4.00
    print(f"  概算コスト: ${cost_in + cost_out:.4f}")
    print(f"  所要時間: {elapsed:.0f}秒")
    print(f"  結果: {result_path}")

    # 成功した議員の詳細
    ok_details = [d for d in results["details"] if d["status"] == "ok"]
    if ok_details:
        print(f"\n抽出結果:")
        for d in ok_details:
            print(f"  {d['politician']}: {d['transactions']}件 ({d['pdfs']}PDF, {d['years']})")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="汎用トランザクション抽出")
    parser.add_argument("politician", nargs="?", default=None, help="議員名（省略時はバッチモード）")
    parser.add_argument("--year", type=str, default=None, help="対象年（省略時は全年）")
    parser.add_argument("--batch", type=int, default=None, help="バッチ実行（0=全員, N=先頭N名）")
    parser.add_argument("--resume", action="store_true", help="処理済みスキップ")
    parser.add_argument("--list", action="store_true", help="PDF取得済み議員一覧を表示")
    args = parser.parse_args()

    if args.list:
        politicians = list_all_politicians_with_pdfs()
        print(f"PDF取得済み議員: {len(politicians)}名")
        for p in politicians:
            pdfs = scan_politician_pdfs(p)
            years = sorted(set(x["year"] for x in pdfs))
            print(f"  {p}: {len(pdfs)}PDF ({years})")
        sys.exit(0)

    if args.batch is not None:
        run_batch(limit=args.batch if args.batch > 0 else None, resume=args.resume)
    elif args.politician:
        print("=" * 60)
        print(f"PoliMirror - トランザクション抽出 v1.0.0")
        print(f"対象: {args.politician}")
        print(f"モデル: {MODEL}")
        print("=" * 60)

        client = anthropic.Anthropic()
        result = extract_politician(args.politician, client)

        if result:
            print(f"\n完了: {result['total_transactions']}件")
            cost_in = result['tokens_in'] / 1_000_000 * 0.80
            cost_out = result['tokens_out'] / 1_000_000 * 4.00
            print(f"API: {result['tokens_in']:,}入力 + {result['tokens_out']:,}出力 (${cost_in+cost_out:.4f})")
        else:
            print("[ERROR] 抽出失敗")
    else:
        parser.print_help()
