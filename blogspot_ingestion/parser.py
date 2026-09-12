"""Atom XML and Google Takeout parser for Blogger / Blogspot exports."""

import csv
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


def resolve_feed_path(path_input: str | Path) -> Path:
    """Resolve a file or directory path to a valid Blogger Atom/XML feed file."""
    p = Path(path_input).resolve()
    if p.is_file():
        return p

    if p.is_dir():
        # Priority order for Google Takeout and Blogger exports
        candidate_names = ["feed.atom", "atom.feed"]
        for name in candidate_names:
            candidate = p / name
            if candidate.is_file():
                return candidate

        # Check in standard subdirectories (e.g. Blogger/Blogs/<BlogName>/feed.atom)
        for pattern in ["feed.atom", "atom.feed", "*.atom", "*.xml"]:
            matches = list(p.glob(f"**/{pattern}"))
            # Filter out comments feed or theme layout files
            valid_matches = [
                m for m in matches
                if not m.name.startswith("theme-")
                and "Comments" not in m.parts
            ]
            if valid_matches:
                return valid_matches[0]
            elif matches:
                return matches[0]

        raise FileNotFoundError(
            f"No feed.atom, atom.feed, or XML archive found inside directory: {p}"
        )

    raise FileNotFoundError(f"Input path does not exist: {p}")


def detect_base_url_from_settings(feed_file: Path) -> Optional[str]:
    """Attempt to detect canonical blog base URL from an adjacent settings.csv file."""
    settings_file = feed_file.parent / "settings.csv"
    if not settings_file.is_file():
        # Also check parent directory
        settings_file = feed_file.parent.parent / "settings.csv"

    if settings_file.is_file():
        try:
            with open(settings_file, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                row = next(reader, None)
                if row:
                    subdomain = row.get("blog_subdomain", "").strip()
                    if subdomain:
                        return f"https://{subdomain}.blogspot.com"
        except Exception:
            pass

    return None


class BloggerXmlParser:
    """Read-only parser for both Google Takeout (feed.atom / atom.feed) and legacy Blogger XML exports."""

    ATOM_KIND_SCHEME = "http://schemas.google.com/g/2005#kind"
    LEGACY_LABEL_SCHEME = "http://www.blogger.com/atom/ns#"
    KNOWN_KINDS = {"post", "comment", "page", "template", "settings"}

    def __init__(self, path_input: str | Path, base_url: Optional[str] = None):
        self.xml_path = resolve_feed_path(path_input)
        self.base_url = base_url or detect_base_url_from_settings(self.xml_path)

    def parse_entries(self) -> Generator[Tuple[BlogPost, List[IngestionIssue]], None, None]:
        """Parse all entries from the feed yielding (BlogPost, issues)."""
        tree = ET.parse(str(self.xml_path))
        root = tree.getroot()

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
        filename_url: Optional[str] = None
        alternate_urls: List[str] = []
        labels: List[str] = []
        content_html = ""
        author_name: Optional[str] = None
        author_email: Optional[str] = None
        is_draft = False
        is_trashed = False
        kind = "post"
        explicit_type_found = False

        for child in entry_el:
            tag_name = _local_tag(child)
            tag_text = (child.text or "").strip()

            if tag_name == "id":
                post_id = tag_text

            elif tag_name == "title":
                title = tag_text

            elif tag_name == "published":
                published = tag_text

            elif tag_name == "updated":
                updated = tag_text

            elif tag_name == "created" and not published:
                # Fallback to creation date if published is absent
                published = tag_text

            elif tag_name == "content":
                content_html = child.text or ""

            elif tag_name == "type":
                # Google Takeout Atom uses <type>POST</type>, <type>COMMENT</type>, <type>PAGE</type>
                if tag_text:
                    kind = tag_text.lower()
                    explicit_type_found = True

            elif tag_name == "status":
                # Google Takeout Atom uses <status>LIVE</status>, <status>DRAFT</status>, <status>TRASHED</status>
                status_upper = tag_text.upper()
                if status_upper == "DRAFT":
                    is_draft = True
                elif status_upper == "TRASHED":
                    is_trashed = True

            elif tag_name == "trashed":
                # Google Takeout: empty tag if live, or timestamp/true if deleted
                if tag_text and tag_text.lower() not in ("", "false", "0", "none"):
                    is_trashed = True

            elif tag_name == "filename":
                # Google Takeout stores post permalink path in <filename> e.g. /2025/05/post.html
                if tag_text and tag_text.startswith("/"):
                    filename_url = tag_text

            elif tag_name == "author":
                for author_child in child:
                    author_tag = _local_tag(author_child)
                    if author_tag == "name":
                        author_name = (author_child.text or "").strip()
                    elif author_tag == "email":
                        author_email = (author_child.text or "").strip()

            elif tag_name == "category":
                scheme = child.attrib.get("scheme", "")
                term = child.attrib.get("term", "").strip()

                if not term:
                    continue

                if scheme == self.ATOM_KIND_SCHEME or "#kind" in scheme:
                    # Legacy kind detection
                    if not explicit_type_found:
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

                elif not term.startswith("http://schemas.google.com/"):
                    # Both Google Takeout (scheme="tag:blogger.com...") and legacy (scheme="http://www.blogger.com/atom/ns#")
                    if term not in labels:
                        labels.append(term)

            elif tag_name == "link":
                rel = child.attrib.get("rel", "")
                href = child.attrib.get("href", "").strip()
                link_type = child.attrib.get("type", "")

                if rel == "alternate" and link_type == "text/html" and href:
                    canonical_url = href
                elif rel == "alternate" and href:
                    alternate_urls.append(href)

            elif tag_name == "control":
                # Legacy draft check: <app:control><app:draft>yes</app:draft></app:control>
                for control_child in child:
                    if _local_tag(control_child) == "draft":
                        draft_val = (control_child.text or "").strip().lower()
                        if draft_val in ("yes", "true", "1"):
                            is_draft = True

            elif tag_name in ("in-reply-to", "inReplyTo"):
                if kind == "post" and not explicit_type_found:
                    kind = "comment"

        # Resolve URL priority:
        # 1. Canonical alternate link with href
        # 2. Filename combined with base_url
        # 3. Filename relative path
        # 4. First alternate URL
        if not canonical_url and filename_url:
            if self.base_url:
                canonical_url = f"{self.base_url.rstrip('/')}{filename_url}"
            else:
                canonical_url = filename_url
        elif not canonical_url and alternate_urls:
            canonical_url = alternate_urls[0]

        # Check for unfamiliar entry types
        if kind not in self.KNOWN_KINDS:
            issues.append(
                IngestionIssue(
                    issue_type="unfamiliar_entry_type",
                    message=f"Encountered unfamiliar entry type '{kind}' at index {entry_index}.",
                    post_id=post_id,
                    post_title=title,
                    severity="warning",
                )
            )

        # Fallbacks
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

        if kind == "post" and not title:
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
        elif not title:
            title = f"Untitled {kind.capitalize()} {entry_index}"

        if kind == "post" and not published:
            issues.append(
                IngestionIssue(
                    issue_type="missing_publication_date",
                    message=f"Post '{title}' ({post_id}) is missing a published date.",
                    post_id=post_id,
                    post_title=title,
                    severity="warning",
                )
            )

        if kind == "post" and not is_draft and not is_trashed and not canonical_url:
            issues.append(
                IngestionIssue(
                    issue_type="missing_url",
                    message=f"Published post '{title}' ({post_id}) does not have an alternate html URL link or filename.",
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
            is_trashed=is_trashed,
            kind=kind,
            entry_index=entry_index,
        )

        return post, issues
