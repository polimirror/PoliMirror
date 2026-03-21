"""
PoliMirror - 報道ベース政治資金データ収集 v1.0.0

Wikipedia APIから主要議員の政治資金関連情報を収集し、
data/donations/{議員名}/news_based.json に保存、
各議員のMDファイルに「政治資金」セクションを追記する。

信頼度: ★★★★☆（Wikipedia = 報道記事の二次引用）
"""
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime

import requests

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
DONATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "donations")
POLITICIANS_DIR = os.path.join(PROJECT_ROOT, "quartz", "content", "politicians")

TARGETS = [
    "安倍晋三", "岸田文雄", "河野太郎", "小泉進次郎", "枝野幸男",
    "山本太郎", "蓮舫", "石破茂", "高市早苗", "玉木雄一郎",
]

# 各議員の既知の資金管理団体・政治団体名
KNOWN_ORGS = {
    "安倍晋三": {"fund_org": "晋和会", "faction": "清和政策研究会（安倍派）"},
    "岸田文雄": {"fund_org": "新政治経済研究会", "faction": "宏池会（岸田派）"},
    "河野太郎": {"fund_org": "河野太郎事務所", "faction": "無派閥"},
    "小泉進次郎": {"fund_org": "小泉進次郎事務所", "faction": "無派閥"},
    "枝野幸男": {"fund_org": "革新と共生の会", "faction": "立憲民主党"},
    "山本太郎": {"fund_org": "れいわ新選組", "faction": "れいわ新選組"},
    "蓮舫": {"fund_org": "蓮舫事務所", "faction": "立憲民主党"},
    "石破茂": {"fund_org": "石破茂後援会", "faction": "水月会（石破派）"},
    "高市早苗": {"fund_org": "高市早苗後援会", "faction": "無派閥"},
    "玉木雄一郎": {"fund_org": "国民民主党", "faction": "国民民主党"},
}

WIKI_API = "https://ja.wikipedia.org/w/api.php"
USER_AGENT = "PoliMirror/1.0 (https://polimirror.jp; political transparency project)"
REQUEST_INTERVAL = 2


def fetch_wiki_text(session, name):
    """Wikipedia APIから議員ページのwikitextを取得"""
    try:
        time.sleep(REQUEST_INTERVAL)
        params = {
            "action": "parse",
            "page": name,
            "prop": "wikitext",
            "format": "json",
        }
        resp = session.get(WIKI_API, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"  [WARN] Wikipedia API {resp.status_code}")
            return None
        data = resp.json()
        if "error" in data:
            print(f"  [WARN] Wikipedia error: {data['error'].get('info', '')}")
            return None
        return data.get("parse", {}).get("wikitext", {}).get("*", "")
    except Exception:
        traceback.print_exc()
        return None


def extract_finance_info(wiki_text, name):
    """wikitextから政治資金関連情報を抽出"""
    try:
        info = {
            "fund_management_org": KNOWN_ORGS.get(name, {}).get("fund_org", "未収集"),
            "faction": KNOWN_ORGS.get(name, {}).get("faction", "未収集"),
            "party_events": [],
            "finance_issues": [],
            "donations_reported": [],
        }

        if not wiki_text:
            return info

        # 政治資金パーティー関連
        party_patterns = [
            r'政治資金パーティー[^。\n]{0,300}',
            r'パーティー券[^。\n]{0,200}',
            r'資金集めのパーティー[^。\n]{0,200}',
        ]
        for pat in party_patterns:
            matches = re.findall(pat, wiki_text)
            for m in matches:
                clean = re.sub(r'\[\[([^|\]]+\|)?([^\]]+)\]\]', r'\2', m)
                clean = re.sub(r'<ref[^>]*>.*?</ref>', '', clean, flags=re.DOTALL)
                clean = re.sub(r'<ref[^/]*/?>', '', clean)
                clean = re.sub(r'\{\{[^}]+\}\}', '', clean)
                clean = clean.strip()
                if len(clean) > 20 and clean not in [e["detail"] for e in info["party_events"]]:
                    info["party_events"].append({
                        "detail": clean[:300],
                        "source": "Wikipedia",
                    })

        # 政治資金問題・スキャンダル
        issue_patterns = [
            r'裏金[^。\n]{0,400}',
            r'政治資金規正法[^。\n]{0,300}',
            r'不記載[^。\n]{0,300}',
            r'収支報告書[^。\n]{0,300}[虚偽|訂正|問題]',
            r'桜を見る会[^。\n]{0,400}',
            r'旧統一教会[^。\n]{0,300}',
            r'統一教会[^。\n]{0,300}',
        ]
        for pat in issue_patterns:
            matches = re.findall(pat, wiki_text)
            for m in matches:
                clean = re.sub(r'\[\[([^|\]]+\|)?([^\]]+)\]\]', r'\2', m)
                clean = re.sub(r'<ref[^>]*>.*?</ref>', '', clean, flags=re.DOTALL)
                clean = re.sub(r'<ref[^/]*/?>', '', clean)
                clean = re.sub(r'\{\{[^}]+\}\}', '', clean)
                clean = clean.strip()
                if len(clean) > 30:
                    # 重複チェック（先頭50文字で判定）
                    prefix = clean[:50]
                    if not any(prefix in e["detail"] for e in info["finance_issues"]):
                        info["finance_issues"].append({
                            "detail": clean[:400],
                            "source": "Wikipedia（報道記事引用）",
                            "reliability": "★★★★☆",
                        })

        # 献金関連
        donation_patterns = [
            r'企業献金[^。\n]{0,300}',
            r'政治献金[^。\n]{0,300}',
            r'個人献金[^。\n]{0,200}',
            r'寄[付附][^。\n]{0,200}万円',
        ]
        for pat in donation_patterns:
            matches = re.findall(pat, wiki_text)
            for m in matches:
                clean = re.sub(r'\[\[([^|\]]+\|)?([^\]]+)\]\]', r'\2', m)
                clean = re.sub(r'<ref[^>]*>.*?</ref>', '', clean, flags=re.DOTALL)
                clean = re.sub(r'<ref[^/]*/?>', '', clean)
                clean = re.sub(r'\{\{[^}]+\}\}', '', clean)
                clean = clean.strip()
                if len(clean) > 20:
                    prefix = clean[:50]
                    if not any(prefix in e["detail"] for e in info["donations_reported"]):
                        info["donations_reported"].append({
                            "detail": clean[:300],
                            "source": "Wikipedia（報道記事引用）",
                        })

        # 件数制限（多すぎる場合）
        info["party_events"] = info["party_events"][:5]
        info["finance_issues"] = info["finance_issues"][:8]
        info["donations_reported"] = info["donations_reported"][:5]

        return info
    except Exception:
        traceback.print_exc()
        return {
            "fund_management_org": KNOWN_ORGS.get(name, {}).get("fund_org", "未収集"),
            "faction": KNOWN_ORGS.get(name, {}).get("faction", "未収集"),
            "party_events": [],
            "finance_issues": [],
            "donations_reported": [],
        }


def save_json(name, info):
    """JSONファイルに保存"""
    try:
        out_dir = os.path.join(DONATIONS_DIR, name.replace(" ", ""))
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "news_based.json")

        data = {
            "politician": name,
            "source_type": "news_based",
            "reliability": "★★★★☆",
            "note": "報道記事ベース（Wikipedia経由）・一次情報（政治資金収支報告書）ではない",
            "fund_management_org": info["fund_management_org"],
            "faction": info["faction"],
            "party_events": info["party_events"],
            "finance_issues": info["finance_issues"],
            "donations_reported": info["donations_reported"],
            "collected_at": datetime.now().isoformat(),
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"  [SAVE] {out_path}")
        return out_path
    except Exception:
        traceback.print_exc()
        return None


def find_md_file(name):
    """議員名からMDファイルを探す"""
    try:
        clean_name = name.replace(" ", "").replace("　", "")
        for root, _dirs, files in os.walk(POLITICIANS_DIR):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                basename = fname.replace(".md", "").replace(" ", "").replace("　", "")
                if basename == clean_name:
                    return os.path.join(root, fname)
    except Exception:
        traceback.print_exc()
    return None


def generate_finance_section(name, info):
    """政治資金セクションのHTMLを生成"""
    try:
        lines = []
        lines.append("## 政治資金\n")
        lines.append("> ⚠️ このデータは報道記事ベースです。一次情報（政治資金収支報告書）の収集は準備中です。\n")

        # 基本情報
        lines.append(f"| 項目 | 内容 |")
        lines.append(f"|------|------|")
        lines.append(f"| 資金管理団体 | {info['fund_management_org']} |")
        lines.append(f"| 所属派閥 | {info['faction']} |")
        lines.append("")

        # 政治資金問題
        if info["finance_issues"]:
            lines.append("<details><summary>報道された政治資金問題</summary>\n")
            for issue in info["finance_issues"]:
                detail = issue["detail"][:200]
                lines.append(f"- {detail}")
                lines.append(f"  - 出典: {issue['source']}（{issue.get('reliability', '★★★★☆')}）")
            lines.append("\n</details>\n")
        else:
            lines.append("**政治資金問題**: 主要な報道記録なし\n")

        # パーティー
        if info["party_events"]:
            lines.append("<details><summary>政治資金パーティー関連</summary>\n")
            for event in info["party_events"]:
                lines.append(f"- {event['detail'][:200]}")
            lines.append("\n</details>\n")

        # 献金
        if info["donations_reported"]:
            lines.append("<details><summary>報道された献金情報</summary>\n")
            for d in info["donations_reported"]:
                lines.append(f"- {d['detail'][:200]}")
            lines.append("\n</details>\n")

        lines.append("")
        return "\n".join(lines)
    except Exception:
        traceback.print_exc()
        return ""


def update_md(name, finance_html):
    """MDファイルに政治資金セクションを追記/更新"""
    try:
        md_path = find_md_file(name)
        if not md_path:
            print(f"  [SKIP] MDファイルなし")
            return False

        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 既存の政治資金セクションを削除
        pattern = r"## 政治資金\n.*?(?=\n## |\Z)"
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(pattern, "", content, flags=re.DOTALL)
            content = re.sub(r"\n{3,}", "\n\n", content)

        # 挿入位置: 誠実さスコアの前 or 投票行動の前 or 末尾
        insert_before = None
        for marker in ["## 誠実さスコア", "## 投票行動", "## 発言・活動記録"]:
            if marker in content:
                insert_before = marker
                break

        if insert_before:
            content = content.replace(insert_before, finance_html + insert_before)
        else:
            content = content.rstrip() + "\n\n" + finance_html

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"  [MD] {os.path.basename(md_path)} 更新")
        return True
    except Exception:
        traceback.print_exc()
        return False


def run():
    """メイン処理"""
    try:
        print("=" * 60)
        print("報道ベース政治資金データ収集 v1.0.0")
        print("=" * 60)
        print(f"対象: {len(TARGETS)}名")
        print(f"データソース: Wikipedia API")
        print()

        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

        results = []
        for name in TARGETS:
            print(f"\n[処理] {name}")

            # Wikipedia取得
            wiki_text = fetch_wiki_text(session, name)
            if wiki_text:
                print(f"  [WIKI] {len(wiki_text):,} chars取得")
            else:
                print(f"  [WARN] Wikipedia取得失敗")

            # 情報抽出
            info = extract_finance_info(wiki_text, name)

            counts = (
                f"問題{len(info['finance_issues'])}件, "
                f"パーティー{len(info['party_events'])}件, "
                f"献金{len(info['donations_reported'])}件"
            )
            print(f"  [抽出] {counts}")

            # JSON保存
            save_json(name, info)

            # MD更新
            finance_html = generate_finance_section(name, info)
            update_md(name, finance_html)

            results.append({
                "name": name,
                "issues": len(info["finance_issues"]),
                "events": len(info["party_events"]),
                "donations": len(info["donations_reported"]),
            })

        # サマリー
        print("\n" + "=" * 60)
        print("サマリー")
        print("=" * 60)
        total_issues = sum(r["issues"] for r in results)
        total_events = sum(r["events"] for r in results)
        total_donations = sum(r["donations"] for r in results)
        print(f"収集成功: {len(results)}/{len(TARGETS)}名")
        print(f"政治資金問題: {total_issues}件")
        print(f"パーティー関連: {total_events}件")
        print(f"献金情報: {total_donations}件")
        print()
        for r in results:
            print(f"  {r['name']}: 問題{r['issues']} / パーティー{r['events']} / 献金{r['donations']}")
        print("=" * 60)

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    run()
