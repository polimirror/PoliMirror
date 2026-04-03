"""
PoliMirror - transactions.json に source_url を追加
v1.0.0

各トランザクションの organization フィールドから
京都府選管のPDF URLを紐付ける。

使用法:
  python add_source_urls.py 西田昌司
"""
import json
import os
import sys
import traceback
from datetime import datetime

# === 定数 ===
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")

# 政党支部サブページから手動取得したURL（pref_indexに未登録のもの）
MANUAL_URLS = {
    "自由民主党京都府参議院選挙区第四支部": {
        "2022": "https://www.pref.kyoto.jp/senkan/r5teikikouhyou/documents/4-1083.pdf",
        "2023": "https://www.pref.kyoto.jp/senkan/r6teikikouhyou/documents/5-1084.pdf",
    },
}


def load_pref_index(prefecture, year):
    """都道府県選管インデックスを読み込む"""
    path = os.path.join(DONATIONS_DIR, f"pref_index_{prefecture}_{year}.json")
    if not os.path.exists(path):
        print(f"  [WARN] インデックスなし: {path}")
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        traceback.print_exc()
        return {}


def resolve_url(org_name, year, pref_index):
    """団体名からPDF URLを解決する"""
    # 1. pref_indexから検索
    url = pref_index.get(org_name)
    if url:
        return url

    # 2. 手動マッピングから検索
    manual = MANUAL_URLS.get(org_name, {})
    url = manual.get(str(year))
    if url:
        return url

    return None


def add_source_urls(politician_name, prefecture="京都府"):
    """トランザクションファイルにsource_urlを追加する"""
    base = os.path.join(DONATIONS_DIR, politician_name)
    os.makedirs(LOGS_DIR, exist_ok=True)

    missing_log = []
    total_added = 0
    total_excluded = 0

    for year in ["2022", "2023"]:
        tx_path = os.path.join(base, f"{year}_transactions.json")
        if not os.path.exists(tx_path):
            print(f"  [SKIP] {tx_path} なし")
            continue

        with open(tx_path, encoding="utf-8") as f:
            data = json.load(f)

        pref_index = load_pref_index(prefecture, year)
        transactions = data.get("transactions", [])
        updated = []
        excluded = []

        for t in transactions:
            org = t.get("organization", "")
            url = resolve_url(org, year, pref_index)

            if url:
                t["source_url"] = url
                updated.append(t)
                total_added += 1
            else:
                excluded.append(t)
                total_excluded += 1
                missing_log.append(
                    f"{year} | {org} | {t.get('record_type', '?')} | "
                    f"{t.get('summary1', '')} | {t.get('amount', 0)}"
                )

        data["transactions"] = updated
        data["transaction_count"] = len(updated)
        data["source_urls_added_at"] = datetime.now().isoformat()

        with open(tx_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"  {year}: {len(updated)}件にURL追加, {len(excluded)}件除外")

    # ログ出力
    if missing_log:
        log_path = os.path.join(LOGS_DIR, "missing_source_url.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"# source_url が解決できなかったレコード\n")
            f.write(f"# 生成日時: {datetime.now().isoformat()}\n")
            f.write(f"# 対象: {politician_name}\n\n")
            for line in missing_log:
                f.write(line + "\n")
        print(f"\n  除外ログ: {log_path}")

    return total_added, total_excluded


if __name__ == "__main__":
    politician = sys.argv[1] if len(sys.argv) > 1 else "西田昌司"

    print("=" * 60)
    print(f"PoliMirror - source_url 追加 v1.0.0")
    print(f"対象: {politician}")
    print("=" * 60)

    added, excluded = add_source_urls(politician)

    print(f"\n{'='*60}")
    print(f"結果: {added}件追加, {excluded}件除外")
    print(f"{'='*60}")
