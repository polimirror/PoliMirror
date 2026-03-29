"""
PoliMirror - 政治資金収支報告書 OCRパイプライン
v2.1.0

総務省公開の政治資金収支報告書PDFをOCR処理し、
寄付・パーティー情報を構造化データとして抽出する。

v2.0.0: 131サブページ巡回→PDFインデックス構築方式に刷新
v2.1.0: 議員マッチ+政党本体の2本立て処理。
        都道府県選管管轄の議員はスキップ記録。

対象: pdf_index.jsonにマッチするTOP50名 + 主要8政党本体
保存先: data/donations/{名前}/2023_ocr.json
"""
import json
import os
import re
import time
import traceback
from datetime import datetime
from multiprocessing import Pool

import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io


# === 定数 ===
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
RANKING_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "ambiguous_ranking.json")
DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
TEMP_PDF_DIR = os.path.join(PROJECT_ROOT, "data", "temp_pdf")
PDF_INDEX_PATH = os.path.join(DONATIONS_DIR, "pdf_index.json")

SOUMU_BASE_URL = "https://www.soumu.go.jp/senkyo/seiji_s/seijishikin"
SOUMU_ORIGIN = "https://www.soumu.go.jp"
SS_REPORT_DATE = "SS20231124"
SS_INDEX_URL = f"{SOUMU_BASE_URL}/reports/{SS_REPORT_DATE}/"
HEADERS = {"User-Agent": "PoliMirror/1.0 (https://polimirror.jp)"}
REQUEST_INTERVAL = 5  # 秒（robots.txt遵守: 最低5秒）
POOL_SIZE = 16
TARGET_YEAR = "2023"
OCR_DPI = 300
OCR_LANG = "jpn"

# tesseract設定
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
os.environ["TESSDATA_PREFIX"] = r"C:\Users\deco3\tessdata"

# 政党本体（本部のみ。支部は除外）
PARTY_TARGETS = [
    "自由民主党",
    "立憲民主党",
    "日本維新の会",
    "公明党",
    "国民民主党",
    "日本共産党",
    "れいわ新選組",
    "参政党",
]


# === 正規表現パターン ===
# 個人寄付: "個人からの寄付" セクション内の金額
RE_INDIVIDUAL_AMOUNT = re.compile(
    r"個人[かの]ら[のに]寄附?\s*[合計]*\s*([\d,，]+)\s*円"
)
RE_INDIVIDUAL_COUNT = re.compile(
    r"個人[かの]ら[のに]寄附?\s*.*?(\d+)\s*件"
)

# 企業寄付: "企業名  金額" パターン
RE_CORPORATE_DONATION = re.compile(
    r"((?:株式会社|有限会社|合同会社|一般社団法人|一般財団法人)[\w\s]{2,30})\s+([\d,，]+)\s*円?"
)

# 団体寄付: "団体名  金額" パターン
RE_ORG_DONATION = re.compile(
    r"((?:政治資金|政党支部|後援会|連合会|協会|連盟|組合)[\w\s]{2,30})\s+([\d,，]+)\s*円?"
)

# パーティー: "パーティー名称  収入額" パターン
RE_PARTY_EVENT = re.compile(
    r"([\w\s]{2,30}(?:パーティ[ー一]|セミナー|懇談会|励ます会|感謝の集い|を囲む会))\s+([\d,，]+)\s*円?"
)


def load_top50_politicians():
    """ambiguous_ranking.jsonから使用回数TOP50名を取得"""
    try:
        with open(RANKING_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        politicians = data.get("politicians", [])
        # total_ambiguous（使用回数）でソート済みのはずだが念のため
        politicians_sorted = sorted(
            politicians, key=lambda x: x.get("total_ambiguous", 0), reverse=True
        )
        top50 = politicians_sorted[:50]
        print(f"[INFO] TOP50名を読み込み完了: {len(top50)}名")
        for i, p in enumerate(top50[:5], 1):
            print(f"  {i}. {p['name']} (曖昧語{p['total_ambiguous']}回)")
        if len(top50) > 5:
            print(f"  ... 他{len(top50) - 5}名")
        return top50
    except Exception:
        traceback.print_exc()
        return []


def collect_subpage_urls():
    """SS20231124インデックスページから全131サブページURLを収集"""
    try:
        print(f"[INFO] インデックスページ取得: {SS_INDEX_URL}")
        time.sleep(REQUEST_INTERVAL)
        resp = requests.get(SS_INDEX_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = "Shift_JIS"

        soup = BeautifulSoup(resp.text, "html.parser")
        subpages = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if f"/{SS_REPORT_DATE}/" in href and href.endswith(".html"):
                # 絶対URLに変換
                if href.startswith("/"):
                    full_url = SOUMU_ORIGIN + href
                else:
                    full_url = href
                if full_url not in subpages:
                    subpages.append(full_url)

        print(f"[INFO] サブページ数: {len(subpages)}")
        return subpages
    except Exception:
        traceback.print_exc()
        return []


def scrape_subpage(url):
    """1サブページからPDFリンクと団体名を抽出して返す"""
    entries = []
    try:
        time.sleep(REQUEST_INTERVAL)
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = "Shift_JIS"

        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.lower().endswith(".pdf"):
                continue
            # PDF URLを絶対パスに
            if href.startswith("/"):
                pdf_url = SOUMU_ORIGIN + href
            elif href.startswith("http"):
                pdf_url = href
            else:
                pdf_url = SOUMU_ORIGIN + "/" + href.lstrip("/")

            # リンクテキスト（団体名）を取得
            link_text = a.get_text(strip=True)

            # リンクの周囲テキストも取得（親要素）
            parent = a.find_parent(["td", "li", "div", "p"])
            context_text = parent.get_text(strip=True) if parent else ""

            entries.append({
                "pdf_url": pdf_url,
                "link_text": link_text,
                "context": context_text,
                "source_page": url,
            })
    except Exception:
        traceback.print_exc()
        print(f"[ERROR] サブページ取得失敗: {url}")

    return entries


def build_pdf_index(force=False):
    """
    全131サブページを巡回してPDFインデックスを構築。
    結果を data/donations/pdf_index.json に保存。

    force=True: キャッシュを無視して再構築
    戻り値: {団体名: [PDF URL, ...], ...}
    """
    # キャッシュチェック
    if not force and os.path.exists(PDF_INDEX_PATH):
        try:
            with open(PDF_INDEX_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            total_pdfs = sum(len(v) for v in cached["index"].values())
            print(f"[INFO] キャッシュ済みインデックス使用: {len(cached['index'])}団体, {total_pdfs} PDF")
            return cached["index"]
        except Exception:
            traceback.print_exc()
            print("[WARN] キャッシュ読み込み失敗、再構築します")

    print("[INFO] === PDFインデックス構築開始 ===")

    # STEP1: サブページURL一覧を取得
    subpages = collect_subpage_urls()
    if not subpages:
        print("[FATAL] サブページが見つかりません")
        return {}

    # STEP2: 各サブページを巡回してPDFリンク収集
    all_entries = []
    success_count = 0
    fail_count = 0
    for i, page_url in enumerate(subpages, 1):
        print(f"[{i}/{len(subpages)}] {page_url.split(SS_REPORT_DATE + '/')[1] if SS_REPORT_DATE in page_url else page_url}")
        entries = scrape_subpage(page_url)
        if entries:
            all_entries.extend(entries)
            success_count += 1
        else:
            fail_count += 1
        if i % 20 == 0:
            print(f"  ... 累計PDF: {len(all_entries)}件")

    print(f"[INFO] 巡回完了: 成功{success_count}, 失敗{fail_count}, 総PDF数{len(all_entries)}")

    # STEP3: 団体名→PDF URLのマッピングを構築
    index = {}
    for entry in all_entries:
        # link_textかcontextから団体名を取得
        name = entry["link_text"] if entry["link_text"] else entry["context"]
        name = name.strip()
        if not name:
            name = os.path.basename(entry["pdf_url"])

        if name not in index:
            index[name] = []
        if entry["pdf_url"] not in index[name]:
            index[name].append(entry["pdf_url"])

    # STEP4: 保存
    os.makedirs(DONATIONS_DIR, exist_ok=True)
    output = {
        "created_at": datetime.now().isoformat(),
        "report_date": SS_REPORT_DATE,
        "total_subpages": len(subpages),
        "total_entries": len(all_entries),
        "unique_names": len(index),
        "index": index,
    }
    with open(PDF_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[INFO] インデックス保存: {PDF_INDEX_PATH}")
    print(f"[INFO] {len(index)}団体, {len(all_entries)} PDFリンク")
    return index


def find_pdfs_by_name(politician_name, index=None):
    """
    PDFインデックスから議員名で部分一致検索。
    「岸田文雄」→「岸田文雄後援会」「岸田文雄政経研究会」等にマッチ。

    戻り値: [PDF URL, ...]
    """
    try:
        if index is None:
            if not os.path.exists(PDF_INDEX_PATH):
                print(f"[ERROR] インデックス未構築: {PDF_INDEX_PATH}")
                return []
            with open(PDF_INDEX_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            index = data["index"]

        matched_urls = []
        matched_names = []
        for name, urls in index.items():
            if politician_name in name:
                matched_names.append(name)
                for url in urls:
                    if url not in matched_urls:
                        matched_urls.append(url)

        if matched_urls:
            print(f"[INFO] {politician_name}: {len(matched_names)}団体マッチ -> {len(matched_urls)} PDF")
            for mn in matched_names[:5]:
                print(f"  - {mn}")
            if len(matched_names) > 5:
                print(f"  ... 他{len(matched_names) - 5}団体")
        else:
            print(f"[WARN] {politician_name}: マッチなし")

        return matched_urls
    except Exception:
        traceback.print_exc()
        return []


def find_party_pdfs(party_name, index):
    """
    政党本体のPDFを検索する。
    「自由民主党本部（X／Y）」等の本部PDFのみ抽出（支部除外）。
    日本維新の会・国民民主党は分割なしの1ファイルもある。
    """
    matched_urls = []
    matched_names = []
    for name, urls in index.items():
        if party_name not in name:
            continue
        # 本部PDF判定: 「（X／Y）」を含む or 政党名そのもの（支部・比例区・選挙区を除外）
        is_honbu = "／" in name  # 分割PDF
        is_exact = name == party_name  # 完全一致（維新、国民民主等）
        is_chuou = "中央委員会" in name  # 共産党
        has_branch_kw = any(kw in name for kw in ["支部", "比例", "選挙区", "議員連盟", "同志会"])
        has_other_kw = any(kw in name for kw in ["後援会", "を応援", "を励ます", "と進む", "国会議員団", "から国民を守る"])

        if (is_honbu or is_exact or is_chuou) and not has_branch_kw and not has_other_kw:
            matched_names.append(name)
            matched_urls.extend(urls)

    if matched_urls:
        print(f"[INFO] 政党本体 {party_name}: {len(matched_names)}件, {len(matched_urls)} PDF")
        for mn in matched_names:
            print(f"  - {mn}")
    else:
        print(f"[WARN] 政党本体 {party_name}: マッチなし")

    return matched_urls, matched_names


def build_processing_list(index):
    """
    処理対象リストを構築する。
    1. TOP50議員 → pdf_indexから部分一致検索
    2. 主要8政党 → 本部PDFのみ
    3. 不一致議員は「都道府県選管管轄」として記録

    戻り値: (targets, skipped)
      targets: [{"label": str, "type": "politician"|"party", "pdf_urls": [...], "matched_names": [...]}, ...]
      skipped: [{"name": str, "reason": str}, ...]
    """
    targets = []
    skipped = []

    # 1. TOP50議員
    top50 = load_top50_politicians()
    for p in top50:
        name = p["name"]
        urls = find_pdfs_by_name(name, index)
        if urls:
            matched = [n for n in index if name in n]
            targets.append({
                "label": name,
                "type": "politician",
                "pdf_urls": urls,
                "matched_names": matched,
            })
        else:
            skipped.append({"name": name, "reason": "都道府県選管管轄（総務省届出なし）"})

    # 2. 主要政党本体
    for party in PARTY_TARGETS:
        urls, names = find_party_pdfs(party, index)
        if urls:
            targets.append({
                "label": party,
                "type": "party",
                "pdf_urls": urls,
                "matched_names": names,
            })

    return targets, skipped


def download_pdf(label, pdf_url, suffix=""):
    """PDFをダウンロードしてローカルパスを返す"""
    try:
        os.makedirs(TEMP_PDF_DIR, exist_ok=True)
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", label)
        fname = f"{safe_name}_{TARGET_YEAR}{suffix}.pdf"
        local_path = os.path.join(TEMP_PDF_DIR, fname)

        if os.path.exists(local_path):
            print(f"[INFO] {label}: キャッシュ済みPDF使用 ({fname})")
            return local_path

        time.sleep(REQUEST_INTERVAL)
        resp = requests.get(pdf_url, headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()

        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = os.path.getsize(local_path) / (1024 * 1024)
        print(f"[INFO] {label}: PDF保存完了 ({size_mb:.1f}MB) ({fname})")
        return local_path
    except Exception:
        traceback.print_exc()
        return None


def extract_pdf_text(pdf_path):
    """PyMuPDF + tesseract でPDFからテキストを抽出する。
    テキスト埋め込みPDFはfitzで直接抽出、
    スキャン画像PDFはOCRで処理。"""
    try:
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        print(f"  抽出: {page_count}ページ")

        full_text = ""
        for i, page in enumerate(doc, 1):
            # まずテキスト埋め込みを試行
            text = page.get_text().strip()
            if len(text) > 20:
                full_text += text + "\n"
            else:
                # スキャン画像 → OCR
                pix = page.get_pixmap(dpi=OCR_DPI)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img, lang=OCR_LANG)
                full_text += text + "\n"

            if i % 10 == 0:
                print(f"  抽出: {i}/{page_count}ページ完了")

        doc.close()
        print(f"  抽出: 全{page_count}ページ完了 ({len(full_text)}文字)")
        return full_text
    except Exception:
        traceback.print_exc()
        return ""


def normalize_ocr_numbers(text):
    """OCRで誤認識された丸数字を通常数字に変換"""
    circle_map = {
        "⓪": "0", "①": "1", "②": "2", "③": "3", "④": "4",
        "⑤": "5", "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9",
        "⑩": "10", "⑪": "11", "⑫": "12", "⑬": "13", "⑭": "14",
        "⑮": "15", "⑯": "16", "⑰": "17", "⑱": "18", "⑲": "19",
        "⑳": "20",
    }
    for circle, num in circle_map.items():
        text = text.replace(circle, num)
    return text


def parse_amount(amount_str):
    """カンマ区切り金額文字列を整数に変換"""
    try:
        cleaned = amount_str.replace(",", "").replace("，", "").replace(" ", "")
        return int(cleaned)
    except (ValueError, AttributeError):
        return 0


def extract_donations(ocr_text):
    """OCRテキストから寄付・パーティー情報を抽出"""
    result = {
        "individual_donations": {
            "total_amount": 0,
            "count": 0,
        },
        "corporate_donations": [],
        "organization_donations": [],
        "party_events": [],
    }

    try:
        ocr_text = normalize_ocr_numbers(ocr_text)

        # 個人寄付（総額）
        m = RE_INDIVIDUAL_AMOUNT.search(ocr_text)
        if m:
            result["individual_donations"]["total_amount"] = parse_amount(m.group(1))

        # 個人寄付（件数）
        m = RE_INDIVIDUAL_COUNT.search(ocr_text)
        if m:
            result["individual_donations"]["count"] = int(m.group(1))

        # 企業寄付
        for m in RE_CORPORATE_DONATION.finditer(ocr_text):
            result["corporate_donations"].append({
                "company": m.group(1).strip(),
                "amount": parse_amount(m.group(2)),
            })

        # 団体寄付
        for m in RE_ORG_DONATION.finditer(ocr_text):
            result["organization_donations"].append({
                "organization": m.group(1).strip(),
                "amount": parse_amount(m.group(2)),
            })

        # パーティー
        for m in RE_PARTY_EVENT.finditer(ocr_text):
            result["party_events"].append({
                "event_name": m.group(1).strip(),
                "revenue": parse_amount(m.group(2)),
            })

    except Exception:
        traceback.print_exc()

    return result


def process_target(target):
    """
    1対象分の処理: ダウンロード → OCR → 抽出 → 保存

    target: {"label": str, "type": "politician"|"party",
             "pdf_urls": [...], "matched_names": [...]}
    """
    label = target["label"]
    target_type = target["type"]
    pdf_urls = target["pdf_urls"]

    print(f"\n{'='*50}")
    print(f"[START] {label} ({target_type}, {len(pdf_urls)} PDF)")
    print(f"{'='*50}")

    try:
        # 全PDFをダウンロード → OCR → テキスト結合
        all_ocr_text = ""
        downloaded = 0
        for i, pdf_url in enumerate(pdf_urls):
            suffix = f"_{i+1:02d}" if len(pdf_urls) > 1 else ""
            pdf_path = download_pdf(label, pdf_url, suffix=suffix)
            if not pdf_path:
                print(f"[WARN] {label}: PDF {i+1}/{len(pdf_urls)} ダウンロード失敗")
                continue
            downloaded += 1

            print(f"[抽出] {label}: PDF {i+1}/{len(pdf_urls)} テキスト抽出中...")
            ocr_text = extract_pdf_text(pdf_path)
            if ocr_text:
                all_ocr_text += ocr_text + "\n"

        if not all_ocr_text:
            print(f"[SKIP] {label}: OCRテキスト空（全PDF失敗）")
            return {"name": label, "type": target_type, "status": "skip",
                    "reason": "ocr_empty"}

        # データ抽出
        donations = extract_donations(all_ocr_text)

        # 保存
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", label)
        out_dir = os.path.join(DONATIONS_DIR, safe_name)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{TARGET_YEAR}_ocr.json")

        output_data = {
            "name": label,
            "type": target_type,
            "year": TARGET_YEAR,
            "source": "総務省政治資金収支報告書",
            "source_url": f"https://www.soumu.go.jp/senkyo/seiji_s/seijishikin/reports/{SS_REPORT_DATE}/",
            "matched_organizations": target["matched_names"],
            "pdf_count": len(pdf_urls),
            "pdf_downloaded": downloaded,
            "ocr_processed_at": datetime.now().isoformat(),
            "ocr_text_length": len(all_ocr_text),
            "donations": donations,
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        # 結果サマリ
        corp_count = len(donations["corporate_donations"])
        org_count = len(donations["organization_donations"])
        event_count = len(donations["party_events"])
        print(f"[DONE] {label}: 企業{corp_count}件, 団体{org_count}件, パーティー{event_count}件")
        print(f"  -> {out_path}")

        return {"name": label, "type": target_type, "status": "success",
                "pdf_count": len(pdf_urls), "corporations": corp_count,
                "organizations": org_count, "events": event_count}

    except Exception:
        traceback.print_exc()
        print(f"[ERROR] {label}: 処理失敗")
        return {"name": label, "type": target_type, "status": "error",
                "reason": traceback.format_exc()}


if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("PoliMirror - 政治資金収支報告書 OCRパイプライン v2.1.0")
    print(f"対象年度: {TARGET_YEAR}")
    print("=" * 60)

    # --index-only: インデックス構築のみ実行
    if "--index-only" in sys.argv:
        force = "--force" in sys.argv
        index = build_pdf_index(force=force)
        if index:
            print(f"\n[結果] {len(index)}団体のPDFインデックスを構築")
            print("\n[サンプル10件]")
            for i, (name, urls) in enumerate(list(index.items())[:10], 1):
                print(f"  {i}. {name} ({len(urls)} PDF)")
                for u in urls[:2]:
                    print(f"     {u}")
        sys.exit(0)

    # インデックス読み込み（キャッシュ使用）
    index = build_pdf_index()
    if not index:
        print("[FATAL] PDFインデックスの構築に失敗しました")
        exit(1)

    # 処理対象リスト構築
    targets, skipped = build_processing_list(index)

    total_pdfs = sum(len(t["pdf_urls"]) for t in targets)
    politician_targets = [t for t in targets if t["type"] == "politician"]
    party_targets = [t for t in targets if t["type"] == "party"]

    print("\n" + "=" * 60)
    print("処理対象一覧")
    print("=" * 60)

    print(f"\n【議員】{len(politician_targets)}名, {sum(len(t['pdf_urls']) for t in politician_targets)} PDF")
    for t in politician_targets:
        print(f"  {t['label']}: {len(t['pdf_urls'])} PDF")
        for mn in t["matched_names"]:
            print(f"    - {mn}")

    print(f"\n【政党本体】{len(party_targets)}政党, {sum(len(t['pdf_urls']) for t in party_targets)} PDF")
    for t in party_targets:
        print(f"  {t['label']}: {len(t['pdf_urls'])} PDF")
        for mn in t["matched_names"]:
            print(f"    - {mn}")

    print(f"\n【スキップ（都道府県選管管轄）】{len(skipped)}名")
    for s in skipped:
        print(f"  - {s['name']}")

    print(f"\n合計: {len(targets)}対象, {total_pdfs} PDF")

    # --dry-run: 一覧表示のみ
    if "--dry-run" in sys.argv:
        print("\n[INFO] --dry-run: 処理対象の確認のみ。実行するには --dry-run を外してください。")
        sys.exit(0)

    # === OCR処理実行 ===
    print(f"\n[INFO] PDF処理開始: {len(targets)}対象, {total_pdfs} PDF")
    print(f"  方式: PyMuPDF + tesseract OCR ({OCR_DPI}dpi)")
    print(f"  リクエスト間隔: {REQUEST_INTERVAL}秒\n")

    # 逐次処理（総務省への負荷配慮 + PDF単位でrequest interval遵守）
    results = []
    for i, target in enumerate(targets, 1):
        print(f"\n--- [{i}/{len(targets)}] ---")
        result = process_target(target)
        results.append(result)

    # === 結果集計 ===
    success = [r for r in results if r["status"] == "success"]
    skipped_results = [r for r in results if r["status"] == "skip"]
    errors = [r for r in results if r["status"] == "error"]

    print("\n" + "=" * 60)
    print("処理結果サマリ")
    print("=" * 60)
    print(f"  処理対象数: {len(results)}")
    print(f"  成功: {len(success)}")
    print(f"  スキップ: {len(skipped_results)}")
    print(f"  エラー: {len(errors)}")

    if success:
        print("\n[成功一覧]")
        for s in success:
            print(f"  {s['name']} ({s['type']}): "
                  f"企業{s.get('corporations',0)}件, "
                  f"団体{s.get('organizations',0)}件, "
                  f"パーティー{s.get('events',0)}件")

    if errors:
        print("\n[エラー一覧]")
        for e in errors:
            print(f"  - {e['name']}")

    # 集計結果を保存
    summary_path = os.path.join(DONATIONS_DIR, f"ocr_summary_{TARGET_YEAR}.json")
    summary = {
        "processed_at": datetime.now().isoformat(),
        "target_year": TARGET_YEAR,
        "version": "v2.1.0",
        "total_targets": len(results),
        "total_pdfs_processed": total_pdfs,
        "success": len(success),
        "skipped_ocr": len(skipped_results),
        "errors": len(errors),
        "skipped_prefectural": [s["name"] for s in skipped],
        "results": results,
    }
    os.makedirs(DONATIONS_DIR, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n[INFO] サマリ保存: {summary_path}")
    print("[INFO] 完了")
