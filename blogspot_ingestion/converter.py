"""HTML to Markdown converter engine with selective preservation of complex HTML."""

import html
import re
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup, Comment, Tag
from markdownify import MarkdownConverter

from blogspot_ingestion.models import IngestionIssue


def is_complex_table(table_tag: Tag) -> bool:
    """Determine if a table requires raw HTML preservation due to Markdown table limitations."""
    cells = table_tag.find_all(["td", "th"])
    if not cells:
        return False

    for cell in cells:
        # Check for merged cells (colspan or rowspan > 1)
        colspan = cell.get("colspan")
        if colspan:
            try:
                if int(colspan) > 1:
                    return True
            except (ValueError, TypeError):
                return True

        rowspan = cell.get("rowspan")
        if rowspan:
            try:
                if int(rowspan) > 1:
                    return True
            except (ValueError, TypeError):
                return True

        # Check for nested block-level structures that break Markdown pipe tables
        if cell.find(["table", "ul", "ol", "pre", "blockquote"]):
            return True

    return False


class BloggerMarkdownConverter(MarkdownConverter):
    """Custom Markdown converter that preserves HTML only when necessary and handles Blogger quirks."""

    def __init__(self, **options):
        # Default options: ATX headers, autolinks, strip empty elements
        options.setdefault("heading_style", "atx")
        options.setdefault("bullets", "-")
        options.setdefault("sub_symbol", "")
        options.setdefault("sup_symbol", "")
        options.setdefault("escape_asterisks", False)
        options.setdefault("escape_underscores", False)
        super().__init__(**options)

    # --- Selective HTML Preservation for Elements that cannot be represented cleanly in Markdown ---

    def convert_iframe(self, el: Tag, text: str, *args, **kwargs) -> str:
        """Preserve iframes (YouTube embeds, Vimeo, interactive maps, forms, audio players)."""
        return f"\n\n{str(el).strip()}\n\n"

    def convert_video(self, el: Tag, text: str, *args, **kwargs) -> str:
        """Preserve HTML5 video players."""
        return f"\n\n{str(el).strip()}\n\n"

    def convert_audio(self, el: Tag, text: str, *args, **kwargs) -> str:
        """Preserve HTML5 audio players."""
        return f"\n\n{str(el).strip()}\n\n"

    def convert_object(self, el: Tag, text: str, *args, **kwargs) -> str:
        """Preserve embedded objects."""
        return f"\n\n{str(el).strip()}\n\n"

    def convert_embed(self, el: Tag, text: str, *args, **kwargs) -> str:
        """Preserve plugin embeds."""
        return f"\n\n{str(el).strip()}\n\n"

    def convert_details(self, el: Tag, text: str, *args, **kwargs) -> str:
        """Preserve collapsible <details><summary>...</summary>...</details> blocks."""
        return f"\n\n{str(el).strip()}\n\n"

    def convert_svg(self, el: Tag, text: str, *args, **kwargs) -> str:
        """Preserve raw SVG diagrams/graphics."""
        return f"\n\n{str(el).strip()}\n\n"

    def convert_canvas(self, el: Tag, text: str, *args, **kwargs) -> str:
        """Preserve HTML5 canvas elements."""
        return f"\n\n{str(el).strip()}\n\n"

    def convert_sup(self, el: Tag, text: str, *args, **kwargs) -> str:
        """Preserve superscript as HTML tag for clear mathematical/footnote representation."""
        inner = text.strip()
        return f"<sup>{inner}</sup>" if inner else ""

    def convert_sub(self, el: Tag, text: str, *args, **kwargs) -> str:
        """Preserve subscript as HTML tag."""
        inner = text.strip()
        return f"<sub>{inner}</sub>" if inner else ""

    def convert_table(self, el: Tag, text: str, *args, **kwargs) -> str:
        """Preserve complex tables with colspans/rowspans as HTML; convert clean tables to Markdown."""
        if is_complex_table(el):
            return f"\n\n{str(el).strip()}\n\n"
        # Otherwise fallback to standard Markdown pipe table conversion
        return super().convert_table(el, text, *args, **kwargs)

    def convert_pre(self, el: Tag, text: str, *args, **kwargs) -> str:
        """Convert preformatted text / code blocks to fenced Markdown code blocks with language detection."""
        classes = el.get("class", [])
        if isinstance(classes, str):
            classes = classes.split()

        code_child = el.find("code")
        if code_child and isinstance(code_child, Tag):
            child_classes = code_child.get("class", [])
            if isinstance(child_classes, str):
                child_classes = child_classes.split()
            classes.extend(child_classes)

        raw_classes = " ".join(classes)
        lang = ""

        brush_match = re.search(r"brush:\s*(\w+)", raw_classes, re.IGNORECASE)
        if brush_match:
            lang = brush_match.group(1).lower()

        if not lang:
            for cls in classes:
                cls_lower = cls.lower()
                if cls_lower.startswith(("lang-", "language-")):
                    lang = cls_lower.split("-", 1)[1]
                    break
                elif cls_lower in (
                    "python", "py", "javascript", "js", "html", "css", "sql", "bash", "sh",
                    "json", "xml", "java", "cpp", "c", "csharp", "ts", "typescript", "yaml",
                    "ruby", "go", "rust", "php"
                ):
                    lang = cls_lower
                    break

        code_content = el.get_text()
        code_content = code_content.strip("\r\n")

        return f"\n\n```{lang}\n{code_content}\n```\n\n"


class ContentConverter:
    """High-level HTML to Markdown converter with preprocessing and postprocessing."""

    def __init__(self):
        self.converter = BloggerMarkdownConverter()

    def convert(
        self, raw_html: str, post_id: Optional[str] = None, post_title: Optional[str] = None
    ) -> Tuple[str, List[IngestionIssue]]:
        """Convert raw Blogger HTML content into clean Markdown while preserving required HTML."""
        issues: List[IngestionIssue] = []

        if not raw_html or not raw_html.strip():
            return "", issues

        try:
            # Preprocess HTML with BeautifulSoup
            soup = BeautifulSoup(raw_html, "html.parser")

            # Remove HTML comments
            for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
                comment.extract()

            # 1. Blogger WYSIWYG fix: lift block elements (table, div, ul, ol, p, blockquote, pre) out of headings
            for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
                nested_blocks = h.find_all(["table", "ul", "ol", "p", "blockquote", "pre"])
                for block in nested_blocks:
                    # Move block element to be a sibling immediately after the heading
                    h.insert_after(block)

            # 2. Blogger caption tables: unwrap <table class="tr-caption-container"> into image + caption paragraph
            for caption_tbl in soup.find_all("table", class_=lambda c: c and "tr-caption-container" in c):
                img = caption_tbl.find("img")
                if img:
                    a_tag = caption_tbl.find("a")
                    caption_td = caption_tbl.find("td", class_=lambda c: c and "tr-caption" in c)
                    caption_text = caption_td.get_text(strip=True) if caption_td else ""

                    wrapper = soup.new_tag("div")
                    if a_tag and a_tag.get("href"):
                        link_el = soup.new_tag("a", href=a_tag["href"])
                        img_el = soup.new_tag("img", src=img.get("src", ""), alt=img.get("alt", caption_text))
                        link_el.append(img_el)
                        wrapper.append(link_el)
                    else:
                        img_el = soup.new_tag("img", src=img.get("src", ""), alt=img.get("alt", caption_text))
                        wrapper.append(img_el)

                    if caption_text:
                        p_cap = soup.new_tag("p")
                        em_cap = soup.new_tag("em")
                        em_cap.string = caption_text
                        p_cap.append(em_cap)
                        wrapper.append(p_cap)

                    caption_tbl.replace_with(wrapper)

            # 3. Clean Blogger empty spacer tags like <div><br></div> or <p><br></p>
            for div in soup.find_all(["div", "p"]):
                if not div.find_all(True) and not div.get_text(strip=True):
                    div.decompose()
                elif len(div.contents) == 1 and getattr(div.contents[0], "name", None) == "br":
                    div.decompose()

            # 4. Normalize Blogger image wrappers: <div class="separator" ...><a href="..."><img ... /></a></div>
            for sep_div in soup.find_all("div", class_=lambda c: c and "separator" in c):
                img = sep_div.find("img")
                if img and len(sep_div.find_all(True)) <= 2:
                    sep_div.unwrap()

            # 5. Clean up empty Angular / pasted AI component tags (e.g. <source-footnote>)
            for custom_tag in soup.find_all(["source-footnote", "sources-carousel-inline", "response-element", "model-response"]):
                if not custom_tag.get_text(strip=True) and not custom_tag.find("img"):
                    custom_tag.decompose()
                else:
                    custom_tag.unwrap()

            preprocessed_html = str(soup)

            # Convert using custom markdown converter
            md_text = self.converter.convert(preprocessed_html)

            # Post-process Markdown text
            cleaned_md = self._postprocess_markdown(md_text)

            return cleaned_md, issues

        except Exception as ex:
            issues.append(
                IngestionIssue(
                    issue_type="html_conversion_error",
                    message=f"Failed to cleanly convert HTML content: {str(ex)}",
                    post_id=post_id,
                    post_title=post_title,
                    severity="error",
                )
            )
            return raw_html, issues

    def _postprocess_markdown(self, text: str) -> str:
        """Clean up markdown whitespace, redundant blank lines, and entity artifacts."""
        parts = re.split(r"(```[\s\S]*?```)", text)
        for i in range(0, len(parts), 2):
            parts[i] = html.unescape(parts[i])
            parts[i] = parts[i].replace("\u00a0", " ")

        text = "".join(parts)
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Replace lines containing only whitespace with empty string
        text = re.sub(r"^[ \t]+$", "", text, flags=re.MULTILINE)

        # Collapse 3 or more consecutive newlines into 2
        text = re.sub(r"\n{3,}", "\n\n", text)

        lines = [line.rstrip() for line in text.split("\n")]
        text = "\n".join(lines)

        return text.strip()
