import { QuartzComponent, QuartzComponentConstructor, QuartzComponentProps } from "./types"
import { classNames } from "../util/lang"

const ArticleTitle: QuartzComponent = ({ fileData, displayClass }: QuartzComponentProps) => {
  const title = fileData.frontmatter?.title
  const description = fileData.frontmatter?.description
  if (title) {
    return (
      <>
        <h1 class={classNames(displayClass, "article-title")}>{title}</h1>
        {description && (
          <p class="article-description">{description}</p>
        )}
      </>
    )
  } else {
    return null
  }
}

ArticleTitle.css = `
.article-title {
  margin: 2rem 0 0 0;
}
.article-description {
  font-size: 15px;
  color: #888;
  margin: 8px 0 16px;
  line-height: 1.5;
}
`

export default (() => ArticleTitle) satisfies QuartzComponentConstructor
