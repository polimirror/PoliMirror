"""
PoliMirror - 衆議院議員データ収集
v1.0.0

衆議院公式サイトから現職議員の一覧を取得する。
https://www.shugiin.go.jp/internet/itdb_annai.nsf/html/statics/syu/1giin.htm

ページ構成: あ行(1giin.htm) 〜 わ行(10giin.htm) の10ページ
エンコーディング: Shift_JIS (cp932)
テーブル構造: 2番目のtable、カラム=[氏名, ふりがな, 会派, 選挙区, 当選回数]
"""
import json
import os
import re
import sys
import time
import traceback
import logging
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from pipeline.models.politician import Politician

logger = logging.getLogger(__name__)

BASE_URL = "https://www.shugiin.go.jp/internet/itdb_annai.nsf/html/statics/syu"
PAGE_FILES = [f"{i}giin.htm" for i in range(1, 11)]
USER_AGENT = "PoliMirror/1.0 (https://polimirror.jp)"
REQUEST_INTERVAL = 1  # 秒
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'raw')


def clean_name(raw_name: str) -> str:
    """氏名から「君」「君」や余分な空白を除去する"""
    try:
        name = raw_name.replace('\u3000', ' ').strip()
        name = re.sub(r'君$', '', name).strip()
        # 連続スペースを1つに
        name = re.sub(r'\s+', ' ', name)
        return name
    except Exception:
        traceback.print_exc()
        return raw_name


def clean_kana(raw_kana: str) -> str:
    """ふりがなから改行や余分な空白を除去する"""
    try:
        kana = raw_kana.replace('\n', '').replace('\u3000', ' ').strip()
        kana = re.sub(r'\s+', ' ', kana)
        return kana
    except Exception:
        traceback.print_exc()
        return raw_kana


def parse_terms(raw_terms: str) -> int:
    """当選回数を解析する（例: '14', '1（参2）' → 14, 1）"""
    try:
        match = re.match(r'(\d+)', raw_terms.strip())
        if match:
            return int(match.group(1))
        return 0
    except Exception:
        traceback.print_exc()
        return 0


def build_official_url(page_file: str) -> str:
    """公式ページURLを構築する"""
    return f"{BASE_URL}/{page_file}"


def fetch_page(session: requests.Session, page_file: str) -> Optional[str]:
    """1ページを取得してデコードされたHTMLを返す"""
    url = build_official_url(page_file)
    try:
        time.sleep(REQUEST_INTERVAL)
        response = session.get(url, timeout=30)
        response.raise_for_status()
        # Shift_JIS (cp932) でデコード
        content = response.content.decode('cp932', errors='replace')
        logger.info(f"ページ取得成功: {url} ({len(content)} chars)")
        return content
    except requests.exceptions.RequestException as e:
        logger.error(f"ページ取得失敗: {url} - {e}")
        traceback.print_exc()
        return None
    except Exception:
        traceback.print_exc()
        return None


def parse_page(html: str, page_file: str) -> list[Politician]:
    """HTMLから議員データをパースする"""
    politicians = []
    try:
        soup = BeautifulSoup(html, 'lxml')
        tables = soup.find_all('table')

        if len(tables) < 2:
            logger.warning(f"テーブルが見つかりません: {page_file}")
            return politicians

        main_table = tables[1]
        rows = main_table.find_all('tr')

        # 最初の2行はヘッダー
        for i, row in enumerate(rows[2:], start=2):
            try:
                cells = row.find_all('td')
                if len(cells) < 5:
                    logger.warning(f"カラム不足 (row {i}): {len(cells)} cols")
                    continue

                raw_name = cells[0].get_text(strip=True)
                raw_kana = cells[1].get_text()
                raw_party = cells[2].get_text(strip=True)
                raw_constituency = cells[3].get_text(strip=True)
                raw_terms = cells[4].get_text(strip=True)

                name = clean_name(raw_name)
                kana = clean_kana(raw_kana)
                terms = parse_terms(raw_terms)

                if not name:
                    logger.warning(f"氏名が空 (row {i})")
                    continue

                # 一意IDを生成（ふりがなベース）
                id_base = kana.replace(' ', '_')
                pol_id = f"shugiin_{id_base}"

                pol = Politician(
                    id=pol_id,
                    name_ja=name,
                    name_kana=kana,
                    house="衆議院",
                    party=raw_party,
                    constituency=raw_constituency,
                    status="現職",
                    terms=terms,
                    official_page=build_official_url(page_file),
                    last_updated=datetime.now().strftime('%Y-%m-%d'),
                    source_url=build_official_url(page_file),
                )
                politicians.append(pol)

            except Exception:
                logger.error(f"行パースエラー (row {i}, page {page_file})")
                traceback.print_exc()
                continue

        logger.info(f"{page_file}: {len(politicians)}名パース完了")

    except Exception:
        logger.error(f"ページパースエラー: {page_file}")
        traceback.print_exc()

    return politicians


def collect_all() -> list[Politician]:
    """全ページから議員データを収集する"""
    all_politicians = []
    errors = 0

    session = requests.Session()
    session.headers.update({'User-Agent': USER_AGENT})

    for page_file in PAGE_FILES:
        try:
            html = fetch_page(session, page_file)
            if html is None:
                errors += 1
                continue

            politicians = parse_page(html, page_file)
            all_politicians.extend(politicians)
            print(f"  {page_file}: {len(politicians)}名取得")

        except Exception:
            errors += 1
            logger.error(f"ページ処理エラー: {page_file}")
            traceback.print_exc()
            continue

    print(f"\n合計: {len(all_politicians)}名取得 / エラー: {errors}ページ")
    logger.info(f"全ページ収集完了: {len(all_politicians)}名 / エラー: {errors}ページ")
    return all_politicians


def save_to_json(politicians: list[Politician], output_dir: str = OUTPUT_DIR) -> str:
    """収集結果をJSONファイルに保存する"""
    try:
        os.makedirs(output_dir, exist_ok=True)
        date_str = datetime.now().strftime('%Y%m%d')
        filename = f"shugiin_members_{date_str}.json"
        filepath = os.path.join(output_dir, filename)

        data = {
            "collected_at": datetime.now().isoformat(),
            "source": "https://www.shugiin.go.jp",
            "total_count": len(politicians),
            "members": [p.to_dict() for p in politicians],
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"保存完了: {filepath}")
        logger.info(f"JSON保存完了: {filepath} ({len(politicians)}名)")
        return filepath

    except Exception:
        traceback.print_exc()
        raise


def main():
    """メイン実行"""
    try:
        # ログ設定
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)],
        )

        # stdout を UTF-8 に
        sys.stdout.reconfigure(encoding='utf-8')

        print("=" * 60)
        print("PoliMirror - 衆議院議員データ収集 v1.0.0")
        print("=" * 60)
        print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"対象: {len(PAGE_FILES)}ページ (あ行〜わ行)")
        print()

        started_at = datetime.now()

        politicians = collect_all()

        if not politicians:
            print("議員データが取得できませんでした")
            return

        filepath = save_to_json(politicians)

        elapsed = (datetime.now() - started_at).total_seconds()
        print(f"\n{'=' * 60}")
        print(f"完了: {len(politicians)}名")
        print(f"所要時間: {elapsed:.1f}秒")
        print(f"出力: {filepath}")
        print(f"{'=' * 60}")

    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
