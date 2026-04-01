"""
PoliMirror - 議員立法・質問主意書データ収集
v1.0.0

参議院の議案ページ・質問主意書ページから
指定議員のデータを全回次から収集する。

使用法:
  python legislation_collector.py 西田昌司
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

# === 定数 ===
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
LEGISLATION_DIR = os.path.join(PROJECT_ROOT, "data", "legislation")

# 参議院の質問主意書ベースURL
SYUISYO_BASE = "https://www.sangiin.go.jp/japanese/joho1/kousei/syuisyo/{session}/syuisyo.htm"
# 参議院の議案ベースURL
GIAN_BASE = "https://www.sangiin.go.jp/japanese/joho1/kousei/gian/{session}/gian.htm"

# 西田昌司: 2007年初当選 = 第168回国会〜
# 現在の最新回次
LATEST_SESSION = 221
# 参議院議員の検索開始回次
DEFAULT_START_SESSION = 168

HEADERS = {
    "User-Agent": "PoliMirror/1.0 (Political Transparency Database; +https://github.com/polimirror/PoliMirror)",
}
REQUEST_INTERVAL = 5  # CLAUDE.mdルール: 最低5秒


def fetch_questions_for_session(session, target_name):
    """1回次の質問主意書ページから対象議員の質問を抽出"""
    url = SYUISYO_BASE.format(session=session)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"

        soup = BeautifulSoup(resp.text, "html.parser")
        questions = []

        # テーブル構造: 各質問は3行で構成
        # 行1: [提出番号ヘッダ, 件名, (件名続き)]
        # 行2: [番号, "提出者", 提出者名, 質問本文リンク, 答弁リンク]
        # 行3: [PDF質問, PDF答弁]
        all_rows = soup.find_all("tr")
        current_title = ""
        current_title_link = ""

        for tr in all_rows:
            tds = tr.find_all(["td", "th"])
            if not tds:
                continue

            texts = [td.get_text(strip=True) for td in tds]

            # 件名行を検出 (3セル: ["提出番号", "件名", 実際の件名テキスト])
            if len(tds) == 3 and texts[0] == "提出番号":
                current_title = texts[2]
                title_td = tds[2]
                a = title_td.find("a")
                if a and a.get("href"):
                    href = a["href"]
                    if not href.startswith("http"):
                        href = f"https://www.sangiin.go.jp/japanese/joho1/kousei/syuisyo/{session}/{href}"
                    current_title_link = href
                continue

            # 提出者行を検出 (5セル: [番号, "提出者", 名前, 質問HTML, 答弁HTML])
            if len(tds) >= 3 and len(texts) > 1 and "提出者" in texts[1]:
                submitter = texts[2] if len(texts) > 2 else ""
                number = texts[0]
                if target_name in submitter:
                    # 質問本文URLを取得
                    question_url = ""
                    for td in tds:
                        a = td.find("a")
                        if a and "質問本文" in (a.get_text(strip=True) or ""):
                            href = a.get("href", "")
                            if href and not href.startswith("http"):
                                href = f"https://www.sangiin.go.jp/japanese/joho1/kousei/syuisyo/{session}/{href}"
                            question_url = href
                            break

                    questions.append({
                        "session": session,
                        "number": number,
                        "title": current_title,
                        "submitter": submitter.replace("\u3000", " "),
                        "url": question_url or current_title_link,
                    })

        return questions
    except requests.exceptions.HTTPError:
        return []
    except Exception:
        traceback.print_exc()
        return []


def fetch_bills_for_session(session, target_name):
    """1回次の議案ページから対象議員が関わった法案を抽出"""
    url = GIAN_BASE.format(session=session)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"

        soup = BeautifulSoup(resp.text, "html.parser")
        bills = []

        # 参法（参議院議員提出法案）セクションを探す
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue

            # 経過ページのリンクから提出者情報を確認する必要があるが
            # まずは件名を取得
            text = tr.get_text()

            # 番号と件名を取得
            number = tds[0].get_text(strip=True) if len(tds) > 0 else ""
            title = tds[1].get_text(strip=True) if len(tds) > 1 else ""
            status = ""
            keika_link = ""

            for td in tds:
                a = td.find("a")
                if a and "経過" in (a.get_text(strip=True) or ""):
                    href = a.get("href", "")
                    if href and not href.startswith("http"):
                        href = f"https://www.sangiin.go.jp{href}"
                    keika_link = href

            if len(tds) > 2:
                status = tds[-1].get_text(strip=True)

            if number and title:
                bills.append({
                    "session": session,
                    "number": number,
                    "title": title,
                    "status": status,
                    "keika_url": keika_link,
                })

        return bills
    except requests.exceptions.HTTPError:
        return []
    except Exception:
        traceback.print_exc()
        return []


def check_bill_proposer(keika_url, target_name):
    """法案の経過ページから提出者を確認する"""
    if not keika_url:
        return False
    try:
        resp = requests.get(keika_url, headers=HEADERS, timeout=30)
        resp.encoding = resp.apparent_encoding or "utf-8"
        return target_name in resp.text
    except Exception:
        return False


def collect_all(politician_name, start_session=DEFAULT_START_SESSION):
    """全回次から議員のデータを収集する"""
    out_dir = os.path.join(LEGISLATION_DIR, politician_name)
    os.makedirs(out_dir, exist_ok=True)

    all_questions = []
    all_bills = []
    sessions_checked = 0

    print(f"\n  質問主意書の収集（第{start_session}回〜第{LATEST_SESSION}回）")
    for session in range(start_session, LATEST_SESSION + 1):
        questions = fetch_questions_for_session(session, politician_name)
        if questions:
            print(f"    第{session}回: {len(questions)}件発見")
            all_questions.extend(questions)
        sessions_checked += 1
        time.sleep(REQUEST_INTERVAL)

    print(f"  質問主意書: 合計{len(all_questions)}件 ({sessions_checked}回次チェック)")

    # 質問主意書を保存
    q_path = os.path.join(out_dir, "questions.json")
    with open(q_path, "w", encoding="utf-8") as f:
        json.dump({
            "politician": politician_name,
            "collected_at": datetime.now().isoformat(),
            "total": len(all_questions),
            "questions": all_questions,
        }, f, ensure_ascii=False, indent=2)
    print(f"  -> {q_path}")

    # 議案の収集（参法のみ・提出者確認が必要で時間がかかるため別途）
    # ここでは質問主意書のみを確実に取得
    b_path = os.path.join(out_dir, "bills.json")
    with open(b_path, "w", encoding="utf-8") as f:
        json.dump({
            "politician": politician_name,
            "collected_at": datetime.now().isoformat(),
            "total": len(all_bills),
            "note": "議員立法の提出者確認には個別の経過ページ参照が必要。今後実装予定。",
            "bills": all_bills,
        }, f, ensure_ascii=False, indent=2)
    print(f"  -> {b_path}")

    return all_questions, all_bills


if __name__ == "__main__":
    politician = sys.argv[1] if len(sys.argv) > 1 else "西田昌司"

    print("=" * 60)
    print(f"PoliMirror - 議員立法・質問主意書収集 v1.0.0")
    print(f"対象: {politician}")
    print(f"リクエスト間隔: {REQUEST_INTERVAL}秒")
    print("=" * 60)

    questions, bills = collect_all(politician)

    print(f"\n{'='*60}")
    print(f"結果サマリー")
    print(f"{'='*60}")
    print(f"  質問主意書: {len(questions)}件")
    print(f"  議員立法: {len(bills)}件")

    if questions:
        print(f"\n  質問主意書一覧:")
        for q in questions:
            print(f"    第{q['session']}回 | {q['title'][:50]}")
