import { QuartzConfig } from "./quartz/cfg"
import * as Plugin from "./quartz/plugins"

/**
 * Quartz 4 Configuration
 *
 * See https://quartz.jzhao.xyz/configuration for more information.
 */
const config: QuartzConfig = {
  configuration: {
    pageTitle: "PoliMirror",
    pageTitleSuffix: " | 政治の鏡",
    enableSPA: true,
    enablePopovers: true,
    analytics: null,
    locale: "ja-JP",
    baseUrl: "polimirror.pages.dev",
    ignorePatterns: ["private", "templates", ".obsidian", "_template"],
    defaultDateType: "modified",
    theme: {
      fontOrigin: "googleFonts",
      cdnCaching: true,
      typography: {
        header: "Noto Serif JP",
        body: "Noto Sans JP",
        code: "JetBrains Mono",
      },
      colors: {
        lightMode: {
          light: "#f7f7f5",
          lightgray: "#e8e8e4",
          gray: "#9a9a94",
          darkgray: "#4a4a44",
          dark: "#1a1a18",
          secondary: "#1a4fa0",
          tertiary: "#2d6fd6",
          highlight: "rgba(26, 79, 160, 0.06)",
          textHighlight: "rgba(26, 79, 160, 0.15)",
        },
        darkMode: {
          light: "#f7f7f5",
          lightgray: "#e8e8e4",
          gray: "#9a9a94",
          darkgray: "#4a4a44",
          dark: "#1a1a18",
          secondary: "#1a4fa0",
          tertiary: "#2d6fd6",
          highlight: "rgba(26, 79, 160, 0.06)",
          textHighlight: "rgba(26, 79, 160, 0.15)",
        },
      },
    },
  },
  plugins: {
    transformers: [
      Plugin.FrontMatter(),
      Plugin.CreatedModifiedDate({
        priority: ["frontmatter", "git", "filesystem"],
      }),
      Plugin.SyntaxHighlighting({
        theme: {
          light: "github-light",
          dark: "github-dark",
        },
        keepBackground: false,
      }),
      Plugin.ObsidianFlavoredMarkdown({ enableInHtmlEmbed: false }),
      Plugin.GitHubFlavoredMarkdown(),
      Plugin.TableOfContents(),
      Plugin.CrawlLinks({ markdownLinkResolution: "shortest" }),
      Plugin.Description(),
      Plugin.Latex({ renderEngine: "katex" }),
    ],
    filters: [Plugin.RemoveDrafts()],
    emitters: [
      Plugin.AliasRedirects(),
      Plugin.ComponentResources(),
      Plugin.ContentPage(),
      Plugin.FolderPage(),
      Plugin.TagPage(),
      Plugin.ContentIndex({
        enableSiteMap: true,
        enableRSS: true,
      }),
      Plugin.Assets(),
      Plugin.Static(),
      Plugin.Favicon(),
      Plugin.NotFoundPage(),
      // Comment out CustomOgImages to speed up build time
      Plugin.CustomOgImages(),
    ],
  },
}

export default config
