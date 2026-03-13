"""
PoliMirror - 参議院議員データ収集
v1.0.0

参議院公式サイトから現職議員の一覧を取得する。
https://www.sangiin.go.jp/japanese/joho1/kousei/giin/216/giin.htm

ページ構成: 1ページに全議員（50音順テーブル）
エンコーディング: UTF-8
テーブル構造: 2番目のtable (class="list", summary="議員一覧（50音順）")
  ヘッダー(7列): [空, 議員氏名, 読み方, 会派, 選挙区, 任期満了, 空]
  データ(6列):   [議員氏名(リンク付), 読み方, 会派, 選挙区, 任期満了, 空]
  ※ 行頭マーカー（あ/か/さ等）はrowspanで別セル
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from pipeline.models.politician import Politician

logger = logging.getLogger(__name__)

# 参議院は国会回次ごとにURLが変わる
# 最新の回次を自動検出するため、降順で試行する
SANGIIN_BASE = "https://www.sangiin.go.jp/japanese/joho1/kousei/giin"
PROFILE_BASE = "https://www.sangiin.go.jp/japanese/joho1/kousei/giin/profile"
USER_AGENT = "PoliMirror/1.0 (https://polimirror.jp)"
REQUEST_INTERVAL = 1  # 秒
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'raw')

# 試行する国会回次（新しい順）
SESSION_CANDIDATES = list(range(220, 210, -1))


def find_latest_session_url(session: requests.Session) -> Optional[str]:
    """最新の国会回次ページURLを見つける"""
    try:
        for num in SESSION_CANDIDATES:
            url = f"{SANGIIN_BASE}/{num}/giin.htm"
            time.sleep(REQUEST_INTERVAL)
            resp = session.head(url, timeout=15, allow_redirects=True)
            if resp.status_code == 200:
                logger.info(f"最新の国会回次ページ発見: 第{num}回 ({url})")
                return url
        logger.error("有効な国会回次ページが見つかりませんでした")
        return None
    except Exception:
        traceback.print_exc()
        return None


def clean_name(raw_name: str) -> str:
    """氏名から全角スペースを半角スペースに変換し整形する"""
    try:
        name = raw_name.replace('\u3000', ' ').strip()
        name = re.sub(r'\s+', ' ', name)
        return name
    except Exception:
        traceback.print_exc()
        return raw_name


def clean_kana(raw_kana: str) -> str:
    """ふりがなから全角スペースを半角スペースに変換し整形する"""
    try:
        kana = raw_kana.replace('\u3000', ' ').replace('\n', '').strip()
        kana = re.sub(r'\s+', ' ', kana)
        return kana
    except Exception:
        traceback.print_exc()
        return raw_kana


def build_profile_url(relative_href: str) -> Optional[str]:
    """相対パスからプロフィールURLを構築する"""
    try:
        if not relative_href:
            return None
        # ../profile/XXXXXXX.htm -> full URL
        match = re.search(r'profile/(\w+\.htm)', relative_href)
        if match:
            return f"{PROFILE_BASE}/{match.group(1)}"
        return None
    except Exception:
        traceback.print_exc()
        return None


def fetch_page(session: requests.Session, url: str) -> Optional[str]:
    """ページを取得してHTMLテキストを返す"""
    try:
        time.sleep(REQUEST_INTERVAL)
        response = session.get(url, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        logger.info(f"ページ取得成功: {url} ({len(response.text)} chars)")
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"ページ取得失敗: {url} - {e}")
        traceback.print_exc()
        return None
    except Exception:
        traceback.print_exc()
        return None


def parse_page(html: str, source_url: str) -> list[Politician]:
    """HTMLから議員データをパースする"""
    politicians = []
    try:
        soup = BeautifulSoup(html, 'lxml')
        tables = soup.find_all('table')

        # summary="議員一覧（50音順）" のテーブルを探す
        main_table = None
        for t in tables:
            if '議員一覧' in t.get('summary', ''):
                main_table = t
                break
        if main_table is None and len(tables) >= 2:
            main_table = tables[1]
        if main_table is None:
            logger.error("議員一覧テーブルが見つかりません")
            return politicians

        rows = main_table.find_all('tr')
        logger.info(f"テーブル行数: {len(rows)} (ヘッダー含む)")

        # 最初の行はヘッダー
        for i, row in enumerate(rows[1:], start=1):
            try:
                cells = row.find_all('td')

                # 行頭マーカー行（「あ」「か」等のrowspan付きセル）があると
                # セル数が7になる場合がある。6列のデータ行を基本とする。
                if len(cells) < 5:
                    continue

                # セル数によってオフセット調整
                # 7列: [marker, 氏名, 読み方, 会派, 選挙区, 任期満了, 空]
                # 6列: [氏名, 読み方, 会派, 選挙区, 任期満了, 空]
                if len(cells) >= 7:
                    offset = 1
                else:
                    offset = 0

                name_cell = cells[offset]
                kana_cell = cells[offset + 1]
                party_cell = cells[offset + 2]
                constituency_cell = cells[offset + 3]
                term_cell = cells[offset + 4]

                raw_name = name_cell.get_text(strip=True)
                raw_kana = kana_cell.get_text(strip=True)
                raw_party = party_cell.get_text(strip=True)
                raw_constituency = constituency_cell.get_text(strip=True)
                raw_term_end = term_cell.get_text(strip=True)

                name = clean_name(raw_name)
                kana = clean_kana(raw_kana)

                if not name:
                    continue

                # プロフィールリンク取得
                profile_link = name_cell.find('a')
                profile_href = profile_link.get('href', '') if profile_link else ''
                profile_url = build_profile_url(profile_href)

                # 一意IDを生成
                id_base = kana.replace(' ', '_')
                pol_id = f"sangiin_{id_base}"

                pol = Politician(
                    id=pol_id,
                    name_ja=name,
                    name_kana=kana,
                    house="参議院",
                    party=raw_party,
                    constituency=raw_constituency,
                    status="現職",
                    official_page=profile_url,
                    last_updated=datetime.now().strftime('%Y-%m-%d'),
                    source_url=source_url,
                )
                politicians.append(pol)

            except Exception:
                logger.error(f"行パースエラー (row {i})")
                traceback.print_exc()
                continue

        logger.info(f"パース完了: {len(politicians)}名")

    except Exception:
        logger.error("ページパースエラー")
        traceback.print_exc()

    return politicians


def collect_all() -> list[Politician]:
    """参議院議員データを収集する"""
    session = requests.Session()
    session.headers.update({'User-Agent': USER_AGENT})

    try:
        print("最新の国会回次ページを検索中...")
        url = find_latest_session_url(session)
        if url is None:
            logger.error("有効なページが見つかりませんでした")
            return []

        print(f"取得先: {url}")
        html = fetch_page(session, url)
        if html is None:
            return []

        politicians = parse_page(html, url)
        print(f"取得完了: {len(politicians)}名")
        return politicians

    except Exception:
        traceback.print_exc()
        return []


def save_to_json(politicians: list[Politician], output_dir: str = OUTPUT_DIR) -> str:
    """収集結果をJSONファイルに保存する"""
    try:
        os.makedirs(output_dir, exist_ok=True)
        date_str = datetime.now().strftime('%Y%m%d')
        filename = f"sangiin_members_{date_str}.json"
        filepath = os.path.join(output_dir, filename)

        data = {
            "collected_at": datetime.now().isoformat(),
            "source": "https://www.sangiin.go.jp",
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
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)],
        )
        sys.stdout.reconfigure(encoding='utf-8')

        print("=" * 60)
        print("PoliMirror - 参議院議員データ収集 v1.0.0")
        print("=" * 60)
        print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
