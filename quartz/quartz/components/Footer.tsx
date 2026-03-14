import { QuartzComponentConstructor } from "./types"

export default (() => {
  return () => {
    const today = new Date().toLocaleDateString("ja-JP", {
      year: "numeric", month: "long", day: "numeric"
    })
    return (
      <footer>
        <div class="footer-inner">

          <div class="footer-top">
            <div class="footer-brand">
              <span class="footer-logo">PoliMirror</span>
              <p class="footer-mission">政治家の言葉を、すべて記録する。それだけで、政治は変わる。</p>
            </div>
            <div class="footer-stats">
              <div class="footer-stat">
                <span class="stat-num">712</span>
                <span class="stat-label">収録議員数</span>
              </div>
              <div class="footer-stat">
                <span class="stat-num">43,317+</span>
                <span class="stat-label">収録発言数</span>
              </div>
              <div class="footer-stat">
                <span class="stat-num">★★★★★</span>
                <span class="stat-label">一次情報のみ収録</span>
              </div>
            </div>
          </div>

          <div class="footer-mid">
            <div class="footer-col">
              <h4>データソース</h4>
              <ul>
                <li><a href="https://kokkai.ndl.go.jp/" target="_blank" rel="noopener">国会議事録検索システム</a></li>
                <li><a href="https://www.soumu.go.jp/senkyo/" target="_blank" rel="noopener">総務省・選挙関連情報</a></li>
                <li><a href="https://www.shugiin.go.jp/" target="_blank" rel="noopener">衆議院公式サイト</a></li>
                <li><a href="https://www.sangiin.go.jp/" target="_blank" rel="noopener">参議院公式サイト</a></li>
              </ul>
            </div>
            <div class="footer-col">
              <h4>PoliMirrorについて</h4>
              <ul>
                <li><a href="/docs/about">このサイトについて</a></li>
                <li><a href="/docs/policy">データ収集ポリシー</a></li>
                <li><a href="/docs/reliability">信頼度スコアの基準</a></li>
                <li><a href="/docs/disclaimer">免責事項</a></li>
              </ul>
            </div>
            <div class="footer-col">
              <h4>参加・報告</h4>
              <ul>
                <li><a href="https://github.com/polimirror/PoliMirror/issues" target="_blank" rel="noopener">誤情報・修正報告</a></li>
                <li><a href="https://github.com/polimirror/PoliMirror" target="_blank" rel="noopener">GitHub</a></li>
              </ul>
            </div>
          </div>

          <div class="footer-bottom">
            <p class="footer-disclaimer">
              本サイトは公開情報（国会議事録・官報・公式文書・主要報道機関の署名記事）のみを収録しています。
              各情報には出典・信頼度スコアを明記しています。内容に誤りがある場合は
              <a href="https://github.com/polimirror/PoliMirror/issues" target="_blank" rel="noopener">GitHub Issues</a>
              よりご報告ください。
            </p>
            <p class="footer-copy">
              © 2026 PoliMirror　|　最終更新: {today}　|　是々非々はユーザーが決める。私たちは鏡を置くだけ。
            </p>
          </div>

        </div>
      </footer>
    )
  }
}) satisfies QuartzComponentConstructor
