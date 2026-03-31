"""
PoliMirror - 全議員バッチ献金データ収集
v1.0.0

全715議員に対して、総務省SS20231124(2022年分)・SS20241129(2023年分)の
PDFインデックスから議員名マッチ→PDF DL→OCR→Claude API構造化解析を実行する。

処理済みファイルはスキップ（再実行可能）。
"""
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import anthropic
import fitz
import pytesseract
from PIL import Image
import io as iolib

# === 定数 ===
DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
TEMP_PDF_DIR = os.path.join(PROJECT_ROOT, "data", "temp_pdf")
POLITICIANS_DIR = os.path.join(PROJECT_ROOT, "quartz", "content", "politicians")

SOUMU_BASE_URL = "https://www.soumu.go.jp/senkyo/seiji_s/seijishikin"
SOUMU_ORIGIN = "https://www.soumu.go.jp"
HEADERS = {"User-Agent": "PoliMirror/1.0 (https://polimirror.jp)"}
REQUEST_INTERVAL = 5

OCR_DPI = 300
OCR_LANG = "jpn"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
MAX_TEXT_LEN = 8000

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
os.environ["TESSDATA_PREFIX"] = r"C:\Users\deco3\tessdata"

# 年度別設定: SS公表日 → 対象年度
YEAR_CONFIG = {
    "2022": {"ss_date": "SS20231124", "label": "令和4年分"},
    "2023": {"ss_date": "SS20241129", "label": "令和5年分"},
}

SECTION_KEYWORDS = ["収支の総括表", "収入の部", "寄附", "政治資金パーティー"]

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
- OCRノイズ（丸数字→数字、改行混入、文字化け）を補正して読み取ってください
- 金額は円単位の整数で返してください
- 日付が読み取れない場合は null にしてください
- 該当データがない項目は空配列 [] や 0 を返してください

OCRテキスト（{text_len}文字）:
{ocr_text}
"""


# ============================================================
# インデックス構築
# ============================================================

def build_pdf_index_for_year(year):
    """年度別PDFインデックスを構築。キャッシュがあればスキップ。"""
    cfg = YEAR_CONFIG[year]
    ss_date = cfg["ss_date"]
    index_path = os.path.join(DONATIONS_DIR, f"pdf_index_{year}.json")

    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            print(f"  [{year}] キャッシュ使用: {cached['unique_names']}団体")
            return cached["index"]
        except Exception:
            traceback.print_exc()

    print(f"  [{year}] インデックス構築開始: {ss_date}")
    index_url = f"{SOUMU_BASE_URL}/reports/{ss_date}/"

    # サブページ一覧取得
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(index_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "Shift_JIS"
    soup = BeautifulSoup(resp.text, "html.parser")

    subpages = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if f"/{ss_date}/" in href and href.endswith(".html"):
            full = SOUMU_ORIGIN + href if href.startswith("/") else href
            if full not in subpages:
                subpages.append(full)

    print(f"  [{year}] サブページ: {len(subpages)}")

    # 各サブページからPDFリンク収集
    index = {}
    total_pdfs = 0
    for i, page_url in enumerate(subpages, 1):
        try:
            time.sleep(REQUEST_INTERVAL)
            r = requests.get(page_url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            r.encoding = "Shift_JIS"
            s = BeautifulSoup(r.text, "html.parser")
            for a in s.find_all("a", href=True):
                href = a["href"]
                if not href.lower().endswith(".pdf"):
                    continue
                pdf_url = SOUMU_ORIGIN + href if href.startswith("/") else href
                link_text = a.get_text(strip=True).strip()
                if not link_text:
                    link_text = os.path.basename(pdf_url)
                if link_text not in index:
                    index[link_text] = []
                if pdf_url not in index[link_text]:
                    index[link_text].append(pdf_url)
                    total_pdfs += 1
        except Exception:
            traceback.print_exc()
        if i % 20 == 0:
            print(f"  [{year}] {i}/{len(subpages)} 累計PDF: {total_pdfs}")

    # 保存
    os.makedirs(DONATIONS_DIR, exist_ok=True)
    output = {
        "created_at": datetime.now().isoformat(),
        "report_date": ss_date,
        "year": year,
        "total_subpages": len(subpages),
        "total_entries": total_pdfs,
        "unique_names": len(index),
        "index": index,
    }
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  [{year}] 完了: {len(index)}団体, {total_pdfs} PDF")
    return index


def find_pdfs_for_politician(name, index):
    """議員名で改良マッチング検索（姓+キーワード拡張）"""
    search = name.replace(" ", "").replace("　", "")
    parts = name.split(" ") if " " in name else name.split("　")
    surname = parts[0] if len(parts) >= 2 else search[:2]
    given = parts[1] if len(parts) >= 2 else ""

    matched_urls = []
    matched_names = []
    seen = set()

    for org_name, urls in index.items():
        # 1. フルネーム完全一致
        if search in org_name:
            matched_names.append(org_name)
            for u in urls:
                if u not in seen:
                    matched_urls.append(u)
                    seen.add(u)
            continue

        # 2. 括弧内に議員名が含まれるパターン: "〇〇研究会(姓　名)"
        import re as _re
        paren = _re.findall(r"[（(]([^)）]+)[)）]", org_name)
        for p in paren:
            p_clean = p.replace("　", "").replace(" ", "")
            if search in p_clean or (surname in p_clean and given and given[0] in p_clean):
                matched_names.append(org_name)
                for u in urls:
                    if u not in seen:
                        matched_urls.append(u)
                        seen.add(u)
                break

        # 3. 姓+キーワード + 名の1文字目検証
        if surname in org_name and len(surname) >= 2 and org_name not in matched_names:
            has_kw = any(kw in org_name for kw in [
                "後援会", "事務所", "政経", "を支える", "を応援",
                "を囲む", "を育てる", "研究会", "の会",
            ])
            if has_kw:
                remainder = org_name.replace(surname, "", 1)
                if given and len(given) >= 1 and given[0] in remainder:
                    matched_names.append(org_name)
                    for u in urls:
                        if u not in seen:
                            matched_urls.append(u)
                            seen.add(u)

    return matched_urls, matched_names


# ============================================================
# PDF → テキスト → Claude API
# ============================================================

def download_pdf(url, local_path):
    """PDFダウンロード（キャッシュ対応）"""
    if os.path.exists(local_path):
        return local_path
    try:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        time.sleep(REQUEST_INTERVAL)
        r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
        r.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return local_path
    except Exception:
        traceback.print_exc()
        return None


def extract_text_from_pdf(pdf_path):
    """1つのPDFからテキスト抽出（OCR対応）"""
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            text = page.get_text().strip()
            if len(text) > 20:
                full_text += text + "\n"
            else:
                pix = page.get_pixmap(dpi=OCR_DPI)
                img = Image.open(iolib.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img, lang=OCR_LANG)
                full_text += text + "\n"
            # 十分なテキストが集まったら早期終了
            if len(full_text) > MAX_TEXT_LEN * 3:
                break
        doc.close()
        return full_text
    except Exception:
        traceback.print_exc()
        return ""


def find_relevant_section(text):
    """収支データのセクションを検索"""
    # 丸数字正規化
    circle = {"⓪":"0","①":"1","②":"2","③":"3","④":"4","⑤":"5","⑥":"6","⑦":"7","⑧":"8","⑨":"9"}
    for c, n in circle.items():
        text = text.replace(c, n)

    for kw in SECTION_KEYWORDS:
        pos = text.find(kw)
        if pos >= 0:
            start = max(0, pos - 500)
            end = min(len(text), start + MAX_TEXT_LEN)
            return text[start:end]
    return text[:MAX_TEXT_LEN]


def analyze_with_claude(text, client):
    """Claude APIで構造化解析"""
    try:
        prompt = USER_PROMPT_TEMPLATE.format(text_len=len(text), ocr_text=text)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if not json_match:
            return None, response.usage.input_tokens, response.usage.output_tokens
        result = json.loads(json_match.group(0))
        return result, response.usage.input_tokens, response.usage.output_tokens
    except Exception:
        traceback.print_exc()
        return None, 0, 0


# ============================================================
# メイン処理
# ============================================================

def get_all_politician_names():
    """全議員名をMDファイルから取得"""
    names = []
    for root, dirs, files in os.walk(POLITICIANS_DIR):
        for f in files:
            if f.endswith(".md") and f != "index.md":
                names.append(f.replace(".md", ""))
    return sorted(names)


def process_politician_year(name, year, index, client):
    """1議員×1年度を処理"""
    safe = re.sub(r'[\\/:*?"<>|]', "_", name.replace(" ", ""))
    out_dir = os.path.join(DONATIONS_DIR, safe)
    out_path = os.path.join(out_dir, f"{year}_structured.json")

    # スキップ判定
    if os.path.exists(out_path):
        return "skip"

    # インデックス検索
    urls, org_names = find_pdfs_for_politician(name, index)
    if not urls:
        return "no_match"

    # PDFダウンロード + テキスト抽出
    all_text = ""
    for i, url in enumerate(urls):
        suffix = f"_{i+1:02d}" if len(urls) > 1 else ""
        local = os.path.join(TEMP_PDF_DIR, f"{safe}_{year}{suffix}.pdf")
        path = download_pdf(url, local)
        if path:
            text = extract_text_from_pdf(path)
            all_text += text + "\n"
            if len(all_text) > MAX_TEXT_LEN * 3:
                break

    if not all_text.strip():
        return "ocr_fail"

    # セクション検索 + API解析
    section = find_relevant_section(all_text)
    result, tok_in, tok_out = analyze_with_claude(section, client)
    if not result:
        return "api_fail"

    # 保存
    os.makedirs(out_dir, exist_ok=True)
    output = {
        "name": name.replace(" ", ""),
        "type": "politician",
        "year": year,
        "source": "総務省政治資金収支報告書",
        "analysis_model": CLAUDE_MODEL,
        "analyzed_at": datetime.now().isoformat(),
        "matched_organizations": org_names,
        "pdf_count": len(urls),
        "ocr_text_length": len(all_text),
        "tokens": {"input": tok_in, "output": tok_out},
        "data": result,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return "success"


if __name__ == "__main__":
    print("=" * 60)
    print("PoliMirror - 全議員バッチ献金データ収集 v1.0.0")
    print("=" * 60)

    client = anthropic.Anthropic()

    # Step2: 年度別インデックス構築
    print("\n[インデックス構築]")
    indexes = {}
    for year in ["2022", "2023"]:
        indexes[year] = build_pdf_index_for_year(year)

    # 全議員リスト
    all_names = get_all_politician_names()
    print(f"\n全議員: {len(all_names)}名")

    # マッチ確認
    for year in ["2022", "2023"]:
        matched = sum(1 for n in all_names if find_pdfs_for_politician(n, indexes[year])[0])
        print(f"  {year}年分インデックスでマッチ: {matched}名")

    # バッチ処理
    print(f"\n{'='*60}")
    print("バッチ処理開始")
    print(f"{'='*60}")

    stats = {"success": 0, "skip": 0, "no_match": 0, "ocr_fail": 0, "api_fail": 0}
    total_ops = 0

    for i, name in enumerate(all_names, 1):
        for year in ["2022", "2023"]:
            result = process_politician_year(name, year, indexes[year], client)
            stats[result] += 1
            total_ops += 1

            if result == "success":
                safe = name.replace(" ", "")
                print(f"  [{i}/{len(all_names)}] {name} ({year}): OK")

        # 100件ごとに進捗報告
        if i % 100 == 0:
            print(f"\n--- 進捗: {i}/{len(all_names)}名 ---")
            print(f"  成功: {stats['success']}, スキップ: {stats['skip']}, "
                  f"マッチなし: {stats['no_match']}, OCR失敗: {stats['ocr_fail']}, "
                  f"API失敗: {stats['api_fail']}")
            print()

    # 最終結果
    print(f"\n{'='*60}")
    print("バッチ処理完了")
    print(f"{'='*60}")
    print(f"  総操作数: {total_ops}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
