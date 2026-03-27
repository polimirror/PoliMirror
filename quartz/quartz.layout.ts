import { PageLayout, SharedLayout } from "./quartz/cfg"
import * as Component from "./quartz/components"
import { FileTrieNode } from "./quartz/util/fileTrie"

const folderDisplayNames: Record<string, string> = {
  "docs": "サイト情報",
  "rankings": "ランキング",
  "politicians": "議員データ",
  "地域": "地域別",
}

const mapFn = (node: FileTrieNode) => {
  if (folderDisplayNames[node.displayName]) {
    node.displayName = folderDisplayNames[node.displayName]
  }
}

// components shared across all pages
export const sharedPageComponents: SharedLayout = {
  head: Component.Head(),
  header: [],
  afterBody: [],
  footer: Component.Footer(),
}

// components for pages that display a single page (e.g. a single note)
export const defaultContentPageLayout: PageLayout = {
  beforeBody: [
    Component.ConditionalRender({
      component: Component.Breadcrumbs(),
      condition: (page) => page.fileData.slug !== "index",
    }),
    Component.ArticleTitle(),
    Component.ContentMeta(),
    Component.TagList(),
    Component.TableOfContents(),
  ],
  left: [
    Component.PageTitle(),
    Component.MobileOnly(Component.Spacer()),
    Component.Flex({
      components: [
        {
          Component: Component.Search(),
          grow: true,
        },
        { Component: Component.Darkmode() },
        { Component: Component.ReaderMode() },
      ],
    }),
    Component.Explorer({ folderDefaultState: "open", folderClickBehavior: "link", useSavedState: false, mapFn }),
  ],
  right: [],
}

// components for pages that display lists of pages  (e.g. tags or folders)
export const defaultListPageLayout: PageLayout = {
  beforeBody: [Component.Breadcrumbs(), Component.ArticleTitle(), Component.ContentMeta()],
  left: [
    Component.PageTitle(),
    Component.MobileOnly(Component.Spacer()),
    Component.Flex({
      components: [
        {
          Component: Component.Search(),
          grow: true,
        },
        { Component: Component.Darkmode() },
      ],
    }),
    Component.Explorer({ folderDefaultState: "open", folderClickBehavior: "link", useSavedState: false, mapFn }),
  ],
  right: [],
}
