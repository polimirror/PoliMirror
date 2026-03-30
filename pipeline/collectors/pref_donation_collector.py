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

KANA_BASIC = ["a", "ka", "sa", "ta", "na", "ha", "ma", "ya", "ra", "wa"]
KANA_FULL = [
    "a","i","u","e","o","ka","ki","ku","ke","ko",
    "sa","si","su","se","so","ta","ti","tu","te","to",
    "na","ni","nu","ne","no","ha","hi","hu","he","ho",
    "ma","mi","mu","me","mo","ya","yu","yo",
    "ra","ri","ru","re","ro","wa","wo",
]


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
        # 埼玉県方式: 50音別サブページ（kokkai/shikin/seiji）
        kana_list = year_config.get("kana_list", KANA_FULL)
        for category in ["kokkai", "shikin", "seiji"]:
            pattern = cfg.get(f"{category}_pattern", "")
            if not pattern:
                continue
            for kana in kana_list:
                url = pattern.replace("{kana}", kana)
                pdfs = scrape_pdf_links(url)
                all_pdfs.extend(pdfs)
                if pdfs:
                    print(f"    {category}/{kana}: {len(pdfs)}件")
        # 政党支部ページ
        for party_url in cfg.get("party_pages", []):
            pdfs = scrape_pdf_links(party_url)
            all_pdfs.extend(pdfs)
            if pdfs:
                print(f"    party: {len(pdfs)}件")

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
    """議員名で改良マッチング検索。
    1. フルネーム完全一致
    2. 姓+名の部分一致
    3. 後援会名からの逆引き（「○○太郎後援会」→「○○太郎」）
    4. ひらがな名前での一致（「高木まり」←「高木真理」）
    """
    search = politician_name.replace(" ", "").replace("　", "")
    parts = politician_name.split(" ") if " " in politician_name else politician_name.split("　")
    surname = parts[0] if len(parts) >= 2 else search[:2]
    given = parts[1] if len(parts) >= 2 else ""

    matched = []
    seen_urls = set()

    for org_name, pdf_url in index.items():
        if pdf_url in seen_urls:
            continue

        # 1. フルネーム完全一致
        if search in org_name:
            matched.append((org_name, pdf_url, 1.0))
            seen_urls.add(pdf_url)
            continue

        # 2. 姓一致 + 名の検証（誤マッチ防止）
        if surname in org_name and len(surname) >= 2:
            has_keyword = any(kw in org_name for kw in ["後援会", "事務所", "政経", "を支える", "を応援", "を囲む", "を育てる", "研究会", "の会"])
            if has_keyword:
                remainder = org_name.replace(surname, "", 1)
                if given and len(given) >= 1:
                    # フルネーム or 名の1文字目が団体名に含まれるか
                    if given[0] in remainder:
                        matched.append((org_name, pdf_url, 0.8))
                        seen_urls.add(pdf_url)
                    # 他に同姓の団体がない場合は姓だけで採用
                    elif sum(1 for k in index if surname in k) <= 3:
                        matched.append((org_name, pdf_url, 0.5))
                        seen_urls.add(pdf_url)
                else:
                    matched.append((org_name, pdf_url, 0.6))
                    seen_urls.add(pdf_url)

    return [(name, url) for name, url, _ in sorted(matched, key=lambda x: -x[2])]


MAX_PDFS_PER_POLITICIAN = 3
OCR_TIMEOUT_SEC = 120
MAX_OCR_PAGES = 20


def download_pdf_file(url, label, year):
    """PDFダウンロードのみ。パスを返す。"""
    safe = re.sub(r'[\\/:*?"<>|]', "_", label)
    os.makedirs(TEMP_PDF_DIR, exist_ok=True)
    local_path = os.path.join(TEMP_PDF_DIR, f"{safe}_{year}.pdf")

    if os.path.exists(local_path):
        return local_path
    try:
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


def ocr_pdf_with_timeout(local_path):
    """1 PDFのOCR。MAX_OCR_PAGES制限 + OCR_TIMEOUT_SEC制限。"""
    import signal

    circle = {"⓪":"0","①":"1","②":"2","③":"3","④":"4",
              "⑤":"5","⑥":"6","⑦":"7","⑧":"8","⑨":"9"}
    text = ""
    start_time = time.time()
    try:
        doc = fitz.open(local_path)
        page_count = len(doc)
        pages_to_process = min(page_count, MAX_OCR_PAGES)

        for i, page in enumerate(doc):
            if i >= pages_to_process:
                break
            elapsed = time.time() - start_time
            if elapsed > OCR_TIMEOUT_SEC:
                print(f"      OCRタイムアウト ({OCR_TIMEOUT_SEC}秒超過, {i}p完了)")
                break

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
    except Exception:
        traceback.print_exc()

    for c, n in circle.items():
        text = text.replace(c, n)
    return text


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

            # 都道府県チェック（年度別スキップはメインループで行う）
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

                # PDF DL + OCR（上限3件、タイムアウト付き）
                all_text = ""
                pdfs_processed = 0
                for org_name, pdf_url in matched[:MAX_PDFS_PER_POLITICIAN]:
                    pdf_path = download_pdf_file(pdf_url, f"{safe}_{org_name[:20]}", year)
                    if not pdf_path:
                        continue
                    text = ocr_pdf_with_timeout(pdf_path)
                    if text:
                        all_text += text + "\n"
                        pdfs_processed += 1
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
