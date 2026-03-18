"""
PoliMirror - Claude API 発言分析
v1.0.0

Claude APIを使って国会議事録の発言を分析し、
トピック・スタンス・重要度・感情・キーワード・要約を抽出する。

出力: 同ディレクトリに {speechID}_analysis.json として保存
使用モデル: claude-opus-4-5
"""
import glob
import json
import os
import time
import traceback
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

import anthropic


PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPEECHES_DIR = os.path.join(PROJECT_ROOT, "data", "speeches")

MODEL = "claude-opus-4-5"
API_INTERVAL = 0.5  # 秒

SYSTEM_PROMPT = """あなたは日本の国会議事録の分析専門家です。
与えられた国会発言を分析し、以下のJSON形式で結果を返してください。
JSON以外の文字は一切出力しないでください。

{
  "topics": ["トピック1", "トピック2"],
  "stance": "賛成" or "反対" or "中立" or "不明",
  "importance": 0-100,
  "sentiment": -1.0 ~ 1.0,
  "keywords": ["キーワード1", "キーワード2"],
  "summary": "50文字以内の要約"
}

ルール:
- topics: 発言のトピックタグ。最大5個。具体的な政策名や分野名を使う。
- stance: 発言者が議題に対して取っているスタンス。質疑の場合は質問の方向性から判断。
- importance: 政治的重要度。首相答弁や法案審議=高、手続き的発言=低。
- sentiment: 感情スコア。攻撃的/批判的=-1.0、中立=0.0、肯定的/建設的=1.0。
- keywords: 発言中の重要キーワード。固有名詞・政策名を優先。最大5個。
- summary: 発言の要約。50文字以内。"""


class SpeechAnalyzer:
    """Claude APIを使った発言分析クラス"""

    def __init__(self, model: str = MODEL):
        try:
            self.model = model
            self.client = anthropic.Anthropic()
            print(f"[INFO] SpeechAnalyzer 初期化: model={model}")
        except Exception:
            traceback.print_exc()
            raise

    def analyze(self, speech_data: dict) -> dict | None:
        """1件の発言を分析する"""
        try:
            speech_text = speech_data.get("speech", "")
            if not speech_text or len(speech_text.strip()) < 10:
                print(f"  [SKIP] 発言が短すぎます ({len(speech_text)}文字)")
                return None

            # コンテキスト付きプロンプト
            context = (
                f"発言者: {speech_data.get('speaker', '不明')}\n"
                f"所属: {speech_data.get('speakerGroup', '不明')}\n"
                f"役職: {speech_data.get('speakerPosition', 'なし')}\n"
                f"院: {speech_data.get('nameOfHouse', '不明')}\n"
                f"会議: {speech_data.get('nameOfMeeting', '不明')}\n"
                f"日付: {speech_data.get('date', '不明')}\n"
                f"国会回次: 第{speech_data.get('session', '?')}回\n"
                f"\n--- 発言全文 ---\n{speech_text}"
            )

            # 発言が長すぎる場合は先頭を切り詰め（トークン制限対策）
            if len(context) > 15000:
                context = context[:15000] + "\n\n（以下省略）"

            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": context}],
            )

            result_text = response.content[0].text.strip()

            # JSON部分を抽出（余分な文字がある場合への対策）
            start = result_text.find("{")
            end = result_text.rfind("}") + 1
            if start == -1 or end == 0:
                print(f"  [WARN] JSONが見つかりません: {result_text[:100]}")
                return None

            analysis = json.loads(result_text[start:end])

            # メタデータ追加
            analysis["speechID"] = speech_data.get("speechID", "")
            analysis["model"] = self.model
            analysis["analyzed_at"] = datetime.now().isoformat()
            analysis["input_tokens"] = response.usage.input_tokens
            analysis["output_tokens"] = response.usage.output_tokens

            return analysis

        except json.JSONDecodeError as e:
            print(f"  [FAIL] JSON解析エラー: {e}")
            traceback.print_exc()
            return None
        except Exception:
            traceback.print_exc()
            return None

    def analyze_file(self, filepath: str) -> dict | None:
        """JSONファイル1件を読み込んで分析し、結果を保存する"""
        try:
            # 分析済みファイルがあればスキップ
            base = os.path.splitext(filepath)[0]
            analysis_path = f"{base}_analysis.json"
            if os.path.exists(analysis_path):
                return None  # スキップ

            with open(filepath, "r", encoding="utf-8") as f:
                speech_data = json.load(f)

            analysis = self.analyze(speech_data)
            if analysis is None:
                return None

            with open(analysis_path, "w", encoding="utf-8") as f:
                json.dump(analysis, f, ensure_ascii=False, indent=2)

            return analysis

        except Exception:
            traceback.print_exc()
            return None

    def analyze_recent(self, name: str, days: int = 30) -> dict:
        """指定議員の直近N日分の発言を分析する"""
        stats = {"total": 0, "analyzed": 0, "skipped": 0, "failed": 0}
        try:
            speaker_dir = os.path.join(SPEECHES_DIR, name)
            if not os.path.isdir(speaker_dir):
                print(f"[WARN] ディレクトリが見つかりません: {speaker_dir}")
                return stats

            cutoff = datetime.now() - timedelta(days=days)
            cutoff_str = cutoff.strftime("%Y-%m-%d")
            print(f"[INFO] {name}: {cutoff_str}以降の発言を分析")

            # 全発言ファイルを走査（_analysis.jsonは除外）
            speech_files = []
            for root, _dirs, files in os.walk(speaker_dir):
                for fname in files:
                    if fname.endswith(".json") and "_analysis" not in fname:
                        fpath = os.path.join(root, fname)
                        speech_files.append(fpath)

            # 日付でフィルタリング
            target_files = []
            for fpath in speech_files:
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("date", "") >= cutoff_str:
                        target_files.append(fpath)
                except Exception:
                    traceback.print_exc()

            target_files.sort()
            stats["total"] = len(target_files)
            print(f"[INFO] 対象ファイル: {len(target_files)}件")

            for i, fpath in enumerate(target_files, 1):
                speech_id = os.path.basename(fpath).replace(".json", "")
                print(f"  [{i}/{len(target_files)}] {speech_id}")

                # 分析済みチェック
                base = os.path.splitext(fpath)[0]
                if os.path.exists(f"{base}_analysis.json"):
                    print(f"    → スキップ (分析済み)")
                    stats["skipped"] += 1
                    continue

                result = self.analyze_file(fpath)
                if result:
                    print(f"    → 完了: {result.get('summary', '')}")
                    stats["analyzed"] += 1
                else:
                    stats["failed"] += 1

                time.sleep(API_INTERVAL)

            print(f"[DONE] {name}: 分析={stats['analyzed']} スキップ={stats['skipped']} 失敗={stats['failed']}")
            return stats

        except Exception:
            traceback.print_exc()
            return stats

    def analyze_n_latest(self, name: str, n: int = 5) -> list[dict]:
        """指定議員の最新N件の発言を分析する（テスト用）"""
        results = []
        try:
            speaker_dir = os.path.join(SPEECHES_DIR, name)
            if not os.path.isdir(speaker_dir):
                print(f"[WARN] ディレクトリが見つかりません: {speaker_dir}")
                return results

            # 全発言ファイルを走査して日付順にソート
            speech_files = []
            for root, _dirs, files in os.walk(speaker_dir):
                for fname in files:
                    if fname.endswith(".json") and "_analysis" not in fname:
                        fpath = os.path.join(root, fname)
                        speech_files.append(fpath)

            # ファイル名でソート（日付降順にするため逆順）
            speech_files.sort(reverse=True)
            targets = speech_files[:n]

            print(f"[INFO] {name}: 最新{len(targets)}件を分析")

            for i, fpath in enumerate(targets, 1):
                speech_id = os.path.basename(fpath).replace(".json", "")
                print(f"\n  [{i}/{len(targets)}] {speech_id}")

                result = self.analyze_file(fpath)
                if result:
                    results.append(result)
                    print(f"    topics: {result.get('topics', [])}")
                    print(f"    stance: {result.get('stance', '')}")
                    print(f"    importance: {result.get('importance', 0)}")
                    print(f"    sentiment: {result.get('sentiment', 0)}")
                    print(f"    keywords: {result.get('keywords', [])}")
                    print(f"    summary: {result.get('summary', '')}")
                else:
                    print(f"    → 分析失敗またはスキップ")

                if i < len(targets):
                    time.sleep(API_INTERVAL)

            return results

        except Exception:
            traceback.print_exc()
            return results


def main():
    """テスト実行: 安倍晋三の最新5件を分析"""
    try:
        print("=" * 60)
        print("PoliMirror Speech Analyzer v1.0.0")
        print(f"モデル: {MODEL}")
        print("=" * 60)

        analyzer = SpeechAnalyzer()
        results = analyzer.analyze_n_latest("安倍晋三", n=5)

        print("\n" + "=" * 60)
        print(f"[RESULT] 分析完了: {len(results)}件")
        print("=" * 60)

        if results:
            print("\n--- サンプル出力 (1件目) ---")
            print(json.dumps(results[0], ensure_ascii=False, indent=2))

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    main()
