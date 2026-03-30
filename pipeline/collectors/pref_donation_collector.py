"""
PoliMirror - 都道府県選管 政治資金収支報告書収集
v1.0.0

都道府県選挙管理委員会のPDFインデックスを構築し、
議員名マッチ→PDF DL→OCR→Claude API構造化解析を実行する。
"""
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime
from urllib.parse import urljoin

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

DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
TEMP_PDF_DIR = os.path.join(PROJECT_ROOT, "data", "temp_pdf", "pref")
POLITICIANS_DIR = os.path.join(PROJECT_ROOT, "quartz", "content", "politicians")
PREF_URLS_PATH = os.path.join(DONATIONS_DIR, "prefecture_urls.json")

HEADERS = {"User-Agent": "PoliMirror/1.0 (https://polimirror.jp)"}
REQUEST_INTERVAL = 5
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
MAX_TEXT_LEN = 8000
OCR_DPI = 300
OCR_LANG = "jpn"

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
os.environ["TESSDATA_PREFIX"] = r"C:\Users\deco3\tessdata"

SYSTEM_PROMPT = "政治資金収支報告書のOCRテキストから情報を抽出するアシスタントです。JSONのみ返してください。"
USER_PROMPT = """以下は政治資金収支報告書のOCRテキストです。
以下の情報を抽出してJSONで返してください：
{{
  "individual_donations": {{"total_amount": 金額(整数・円), "count": 件数}},
  "corporate_donations": [{{"name": "企業名", "amount": 金額, "date": "日付"}}],
  "group_donations": [{{"name": "団体名", "amount": 金額, "date": "日付"}}],
  "party_events": [{{"name": "パーティー名", "income": 収入額, "date": "日付"}}],
  "total_income": 収入総額,
  "total_expense": 支出総額
}}
注意：OCRノイズ（丸数字→数字、改行混入）を補正して読み取ってください。金額は円単位整数。該当なしは0か[]。

OCRテキスト:
{text}
"""

KANA_LIST = ["a", "ka", "sa", "ta", "na", "ha", "ma", "ya", "ra", "wa"]


def scrape_pdf_links(url):
    """ページからPDFリンクを収集。[(団体名, PDF URL), ...]"""
    try:
        time.sleep(REQUEST_INTERVAL)
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        r.encoding = r.apparent_encoding
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.lower().endswith(".pdf"):
                continue
            name = a.get_text(strip=True)
            # サイズ表記を除去
            name = re.sub(r"（PDF[：:]?[\d,\.]+KB）", "", name)
            name = re.sub(r"\(PDF[：:]?[\d,\.]+KB\)", "", name)
            name = re.sub(r"（別ウィンドウ.*?）", "", name)
            name = name.strip()
            full_url = urljoin(url, href)
            results.append((name, full_url))
        return results
    except Exception:
        traceback.print_exc()
        return []


def build_pref_index(pref_name, year_config, year):
    """都道府県別PDFインデックスを構築"""
    cache_path = os.path.join(DONATIONS_DIR, f"pref_index_{pref_name}_{year}.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        print(f"  [{pref_name}/{year}] キャッシュ: {len(cached)}件")
        return cached

    cfg = year_config.get(year, {})
    fmt = year_config.get("format", "")
    all_pdfs = []

    if fmt == "kana_subpages":
        # 埼玉県方式: 50音別サブページ
        for category in ["kokkai", "shikin"]:
            pattern = cfg.get(f"{category}_pattern", "")
            if not pattern:
                continue
            for kana in KANA_LIST:
                url = pattern.replace("{kana}", kana)
                pdfs = scrape_pdf_links(url)
                all_pdfs.extend(pdfs)
                if pdfs:
                    print(f"    {category}/{kana}: {len(pdfs)}件")

    elif fmt == "category_subpages":
        # 大阪府方式: カテゴリ別サブページ
        for key in ["kokkai", "shikin"]:
            url = cfg.get(key, "")
            if url:
                pdfs = scrape_pdf_links(url)
                all_pdfs.extend(pdfs)
                print(f"    {key}: {len(pdfs)}件")

    elif fmt == "single_page_pdf_list":
        # 神奈川・北海道方式: 1ページに全PDF
        url = cfg.get("index", "")
        if url:
            pdfs = scrape_pdf_links(url)
            all_pdfs.extend(pdfs)
            print(f"    single_page: {len(pdfs)}件")

    # 保存
    index = {name: url for name, url in all_pdfs}
    os.makedirs(DONATIONS_DIR, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"  [{pref_name}/{year}] {len(index)}件保存")
    return index


def find_politician_pdfs(politician_name, index):
    """議員名で部分一致検索"""
    search = politician_name.replace(" ", "").replace("　", "")
    matched = []
    for org_name, pdf_url in index.items():
        if search in org_name:
            matched.append((org_name, pdf_url))
    return matched


def download_and_ocr(url, label, year):
    """PDF DL→テキスト抽出"""
    safe = re.sub(r'[\\/:*?"<>|]', "_", label)
    os.makedirs(TEMP_PDF_DIR, exist_ok=True)
    local_path = os.path.join(TEMP_PDF_DIR, f"{safe}_{year}.pdf")

    if not os.path.exists(local_path):
        try:
            time.sleep(REQUEST_INTERVAL)
            r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
        except Exception:
            traceback.print_exc()
            return ""

    # OCR
    try:
        doc = fitz.open(local_path)
        text = ""
        circle = {"⓪":"0","①":"1","②":"2","③":"3","④":"4","⑤":"5","⑥":"6","⑦":"7","⑧":"8","⑨":"9"}
        for page in doc:
            t = page.get_text().strip()
            if len(t) > 20:
                text += t + "\n"
            else:
                pix = page.get_pixmap(dpi=OCR_DPI)
                img = Image.open(iolib.BytesIO(pix.tobytes("png")))
                t = pytesseract.image_to_string(img, lang=OCR_LANG)
                text += t + "\n"
            if len(text) > MAX_TEXT_LEN * 3:
                break
        doc.close()
        for c, n in circle.items():
            text = text.replace(c, n)
        return text
    except Exception:
        traceback.print_exc()
        return ""


def find_section(text):
    """収支データセクションを検索"""
    for kw in ["収支の総括表", "収入の部", "寄附", "政治資金パーティー"]:
        pos = text.find(kw)
        if pos >= 0:
            start = max(0, pos - 500)
            return text[start:start + MAX_TEXT_LEN]
    return text[:MAX_TEXT_LEN]


def analyze_claude(text, client):
    """Claude API構造化解析"""
    try:
        prompt = USER_PROMPT.format(text=text[:MAX_TEXT_LEN])
        resp = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        return json.loads(m.group(0))
    except Exception:
        traceback.print_exc()
        return None


def get_unprocessed_politicians(pref_name):
    """指定都道府県の未処理議員リストを返す"""
    pref_names_map = {
        "北海道": "北海道", "東京都": "東京", "大阪府": "大阪",
        "埼玉県": "埼玉", "神奈川県": "神奈川",
    }
    pref_key = pref_names_map.get(pref_name, pref_name.rstrip("都道府県"))

    politicians = []
    for root, dirs, files in os.walk(POLITICIANS_DIR):
        for f in files:
            if not f.endswith(".md") or f == "index.md":
                continue
            md_path = os.path.join(root, f)
            name = f.replace(".md", "")
            safe = name.replace(" ", "")

            # 処理済みチェック
            has_struct = False
            d = os.path.join(DONATIONS_DIR, safe)
            if os.path.isdir(d):
                has_struct = any(fn.endswith("_structured.json") for fn in os.listdir(d))
            if has_struct:
                continue

            # 都道府県チェック
            try:
                with open(md_path, "r", encoding="utf-8") as fh:
                    head = fh.read(500)
                for line in head.split("\n"):
                    if "constituency" in line:
                        val = line.split(":", 1)[1].strip().strip('"')
                        if pref_key in val:
                            politicians.append(name)
                        break
            except Exception:
                pass
    return politicians


if __name__ == "__main__":
    print("=" * 60)
    print("PoliMirror - 都道府県選管 献金データ収集 v1.0.0")
    print("=" * 60)

    with open(PREF_URLS_PATH, "r", encoding="utf-8") as f:
        pref_config = json.load(f)

    client = anthropic.Anthropic()

    # 対象県（東京都除外）
    target_prefs = [p for p in pref_config if pref_config[p].get("format") != "js_dynamic"]
    if "--pref" in sys.argv:
        idx = sys.argv.index("--pref")
        target_prefs = [sys.argv[idx + 1]]

    stats = {"success": 0, "no_match": 0, "ocr_fail": 0, "api_fail": 0, "skip": 0}

    for pref_name in target_prefs:
        cfg = pref_config[pref_name]
        print(f"\n{'='*50}")
        print(f"[{pref_name}]")
        print(f"{'='*50}")

        # 未処理議員取得
        politicians = get_unprocessed_politicians(pref_name)
        print(f"  未処理議員: {len(politicians)}名")

        for year in ["2022", "2023"]:
            # インデックス構築
            print(f"\n  --- {year}年分 ---")
            index = build_pref_index(pref_name, cfg, year)
            if not index:
                print(f"  インデックス空 → スキップ")
                continue

            # 議員ごとに処理
            for pol_name in politicians:
                safe = pol_name.replace(" ", "")
                out_dir = os.path.join(DONATIONS_DIR, safe)
                out_path = os.path.join(out_dir, f"{year}_structured.json")

                if os.path.exists(out_path):
                    stats["skip"] += 1
                    continue

                matched = find_politician_pdfs(pol_name, index)
                if not matched:
                    stats["no_match"] += 1
                    continue

                # PDF DL + OCR
                all_text = ""
                for org_name, pdf_url in matched:
                    text = download_and_ocr(pdf_url, f"{safe}_{org_name[:20]}", year)
                    all_text += text + "\n"
                    if len(all_text) > MAX_TEXT_LEN * 3:
                        break

                if not all_text.strip():
                    stats["ocr_fail"] += 1
                    continue

                section = find_section(all_text)
                result = analyze_claude(section, client)
                if not result:
                    stats["api_fail"] += 1
                    continue

                # 保存
                os.makedirs(out_dir, exist_ok=True)
                output = {
                    "name": safe,
                    "type": "politician",
                    "year": year,
                    "source": f"{pref_name}選挙管理委員会 政治資金収支報告書",
                    "prefecture": pref_name,
                    "analysis_model": CLAUDE_MODEL,
                    "analyzed_at": datetime.now().isoformat(),
                    "matched_organizations": [m[0] for m in matched],
                    "data": result,
                }
                with open(out_path, "w", encoding="utf-8") as fh:
                    json.dump(output, fh, ensure_ascii=False, indent=2)

                print(f"    {pol_name} ({year}): OK [{len(matched)}団体]")
                stats["success"] += 1

        print(f"\n  [{pref_name}] 小計: 成功{stats['success']}")

    print(f"\n{'='*60}")
    print("完了")
    print(f"{'='*60}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
