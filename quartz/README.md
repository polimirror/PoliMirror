# PoliMirror - Quartz公開サイト

## 概要
PoliMirrorの公開サイトは [Quartz v4](https://quartz.jzhao.xyz/) を使用した静的サイトです。

## ローカルビルド

```bash
cd quartz
npm install
npx quartz build
```

ビルド出力: `public/`（プロジェクトルート）

## ローカルプレビュー

```bash
cd public && python -m http.server 8888
# http://localhost:8888 でアクセス
```

## Cloudflare Pagesデプロイ設定
- フレームワーク: なし
- ビルドコマンド: `cd quartz && npm install && npx quartz build`
- ビルド出力: `public`
- 環境変数: `NODE_VERSION` = `22`

## コンテンツ追加
`quartz/content/` にMarkdownファイルを追加する。
Obsidian互換の `[[wiki-link]]` 記法が使用可能。
