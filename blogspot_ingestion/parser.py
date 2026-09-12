"""Atom XML parser for Blogger / Blogspot exports."""

import hashlib
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Generator, List, Optional, Tuple

from blogspot_ingestion.models import BlogPost, IngestionIssue


def compute_file_sha256(filepath: str | Path) -> str:
    """Compute SHA-256 hash of a file for integrity verification."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _local_tag(element: ET.Element) -> str:
    """Extract tag name without XML namespace."""
    tag = element.tag
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


class BloggerXmlParser:
    """Read-only parser for Blogger XML Atom exports."""

    ATOM_KIND_SCHEME = "http://schemas.google.com/g/2005#kind"
    BLOGGER_LABEL_SCHEME = "http://www.blogger.com/atom/ns#"

    def __init__(self, xml_path: str | Path):
        self.xml_path = Path(xml_path).resolve()
        if not self.xml_path.is_file():
            raise FileNotFoundError(f"Blogger XML file not found at: {self.xml_path}")

    def parse_entries(self) -> Generator[Tuple[BlogPost, List[IngestionIssue]], None, None]:
        """Parse all entries from the Blogger XML file yielding (BlogPost, issues)."""
        # ElementTree parse operates strictly in read mode
        tree = ET.parse(str(self.xml_path))
        root = tree.getroot()

        # Iterate over all direct entry elements
        entry_idx = 0
        for child in root:
            if _local_tag(child) == "entry":
                entry_idx += 1
                yield self._parse_entry(child, entry_idx)

    def _parse_entry(self, entry_el: ET.Element, entry_index: int) -> Tuple[BlogPost, List[IngestionIssue]]:
        """Parse an individual <entry> element into a BlogPost model."""
        issues: List[IngestionIssue] = []

        post_id = ""
        title = ""
        published = ""
        updated: Optional[str] = None
        canonical_url: Optional[str] = None
        alternate_urls: List[str] = []
        labels: List[str] = []
        content_html = ""
        author_name: Optional[str] = None
        author_email: Optional[str] = None
        is_draft = False
        kind = "post"

        for child in entry_el:
            tag_name = _local_tag(child)

            if tag_name == "id":
                post_id = (child.text or "").strip()

            elif tag_name == "title":
                title = (child.text or "").strip()

            elif tag_name == "published":
                published = (child.text or "").strip()

            elif tag_name == "updated":
                updated = (child.text or "").strip()

            elif tag_name == "content":
                content_html = child.text or ""

            elif tag_name == "author":
                for author_child in child:
                    author_tag = _local_tag(author_child)
                    if author_tag == "name":
                        author_name = (author_child.text or "").strip()
                    elif author_tag == "email":
                        author_email = (author_child.text or "").strip()

            elif tag_name == "category":
                scheme = child.attrib.get("scheme", "")
                term = child.attrib.get("term", "")

                if scheme == self.ATOM_KIND_SCHEME:
                    # Identify kind: post, comment, page, template, settings
                    if "#comment" in term:
                        kind = "comment"
                    elif "#page" in term:
                        kind = "page"
                    elif "#template" in term:
                        kind = "template"
                    elif "#settings" in term:
                        kind = "settings"
                    elif "#post" in term:
                        kind = "post"
                    else:
                        kind = term.split("#")[-1] if "#" in term else term

                elif scheme == self.BLOGGER_LABEL_SCHEME:
                    # User defined labels / tags
                    label_term = term.strip()
                    if label_term and label_term not in labels:
                        labels.append(label_term)

            elif tag_name == "link":
                rel = child.attrib.get("rel", "")
                href = child.attrib.get("href", "")
                link_type = child.attrib.get("type", "")

                if rel == "alternate" and link_type == "text/html" and href:
                    canonical_url = href.strip()
                elif rel == "alternate" and href:
                    alternate_urls.append(href.strip())

            elif tag_name == "control":
                # Check for draft status: <app:control><app:draft>yes</app:draft></app:control>
                for control_child in child:
                    if _local_tag(control_child) == "draft":
                        draft_val = (control_child.text or "").strip().lower()
                        if draft_val in ("yes", "true", "1"):
                            is_draft = True

            elif tag_name == "in-reply-to":
                # Entry is a comment replying to another post
                if kind == "post":
                    kind = "comment"

        # Resolve URL fallback
        if not canonical_url and alternate_urls:
            canonical_url = alternate_urls[0]

        # Validations and issues recording
        if not post_id:
            post_id = f"generated:entry-{entry_index}"
            issues.append(
                IngestionIssue(
                    issue_type="missing_id",
                    message=f"Entry at index {entry_index} is missing an <id> tag. Assigned fallback: {post_id}",
                    post_id=post_id,
                    post_title=title,
                    severity="warning",
                )
            )

        if not title:
            title = f"Untitled Post {entry_index}"
            issues.append(
                IngestionIssue(
                    issue_type="missing_title",
                    message=f"Post '{post_id}' has no title. Assigned fallback: '{title}'",
                    post_id=post_id,
                    post_title=title,
                    severity="warning",
                )
            )

        if not published:
            issues.append(
                IngestionIssue(
                    issue_type="missing_publication_date",
                    message=f"Post '{title}' ({post_id}) is missing a published date.",
                    post_id=post_id,
                    post_title=title,
                    severity="warning",
                )
            )

        if kind == "post" and not is_draft and not canonical_url:
            issues.append(
                IngestionIssue(
                    issue_type="missing_url",
                    message=f"Published post '{title}' ({post_id}) does not have an alternate html URL link.",
                    post_id=post_id,
                    post_title=title,
                    severity="warning",
                )
            )

        post = BlogPost(
            id=post_id,
            title=title,
            published=published,
            updated=updated,
            url=canonical_url,
            labels=labels,
            content_html=content_html,
            author_name=author_name,
            author_email=author_email,
            is_draft=is_draft,
            kind=kind,
            entry_index=entry_index,
        )

        return post, issues
