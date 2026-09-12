"""Core ingestion pipeline orchestrator for Blogger / Blogspot exports."""

import os
import re
import time
from pathlib import Path
from typing import Dict, Optional, Set
import unicodedata

from blogspot_ingestion.converter import ContentConverter
from blogspot_ingestion.frontmatter import create_post_markdown_content
from blogspot_ingestion.models import ConvertedPostRecord, IngestionReport
from blogspot_ingestion.parser import BloggerXmlParser, compute_file_sha256, resolve_feed_path


def slugify(value: str, max_length: int = 60) -> str:
    """Generate a clean URL/filename-safe slug from a string."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    value = re.sub(r"[-\s]+", "-", value)
    if not value:
        return "post"
    return value[:max_length].rstrip("-")


def extract_date_prefix(date_str: str) -> str:
    """Extract YYYY-MM-DD from an ISO date string."""
    if not date_str:
        return "undated"
    cleaned = date_str.strip()
    if len(cleaned) >= 10 and cleaned[:4].isdigit() and cleaned[4] == "-" and cleaned[7] == "-":
        return cleaned[:10]
    return "undated"


class IngestionPipeline:
    """Orchestrates parsing Blogger feeds, converting content, generating frontmatter, and writing output."""

    def __init__(
        self,
        input_file: str | Path,
        output_dir: str | Path = "output/posts",
        report_json_path: Optional[str | Path] = None,
        report_md_path: Optional[str | Path] = None,
        classification: str = "personal_analysis",
        base_url: Optional[str] = None,
        dry_run: bool = False,
        overwrite: bool = True,
    ):
        self.input_path = Path(input_file).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.report_json_path = (
            Path(report_json_path).resolve()
            if report_json_path
            else self.output_dir.parent / "ingestion_report.json"
        )
        self.report_md_path = (
            Path(report_md_path).resolve()
            if report_md_path
            else self.output_dir.parent / "ingestion_report.md"
        )
        self.classification = classification
        self.base_url = base_url
        self.dry_run = dry_run
        self.overwrite = overwrite

        self.converter = ContentConverter()

    def run(self) -> IngestionReport:
        """Execute the ingestion pipeline."""
        start_time = time.time()

        # Resolve feed file path (handles directory or direct feed.atom/atom.feed/xml file)
        feed_file = resolve_feed_path(self.input_path)

        # Compute initial hash to guarantee input file is unmodified
        initial_hash = compute_file_sha256(feed_file)

        report = IngestionReport(
            input_file=str(feed_file),
            output_dir=str(self.output_dir),
            input_file_hash_sha256=initial_hash,
        )

        if not self.dry_run:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.report_json_path.parent.mkdir(parents=True, exist_ok=True)
            self.report_md_path.parent.mkdir(parents=True, exist_ok=True)

        parser = BloggerXmlParser(feed_file, base_url=self.base_url)

        # Deduplication indices
        seen_post_ids: Dict[str, str] = {}  # post_id -> destination_filename
        seen_urls: Dict[str, str] = {}  # url -> destination_filename
        used_filenames: Set[str] = set()

        for post, parser_issues in parser.parse_entries():
            report.total_entries += 1

            # Record any parser-level issues
            for issue in parser_issues:
                report.add_issue(
                    issue_type=issue.issue_type,
                    message=issue.message,
                    post_id=issue.post_id,
                    post_title=issue.post_title,
                    severity=issue.severity,
                )

            # 1. Filter trashed / deleted entries
            if post.is_trashed:
                report.add_skipped(
                    post_id=post.id,
                    title=post.title,
                    kind="trashed",
                    reason="Skipped trashed/deleted entry",
                )
                continue

            # 2. Filter non-post entries (comments, pages, templates, settings, etc.)
            if post.kind != "post":
                report.add_skipped(
                    post_id=post.id,
                    title=post.title,
                    kind=post.kind,
                    reason=f"Skipped non-post entry kind: '{post.kind}'",
                )
                continue

            # 3. Filter drafts
            if post.is_draft:
                report.add_skipped(
                    post_id=post.id,
                    title=post.title,
                    kind="draft",
                    reason="Skipped draft post (not published)",
                )
                continue

            # This is a published post
            report.published_posts_found += 1

            # 4. Deduplication check
            is_dup = False
            dup_reason = ""
            orig_file = None

            if post.id in seen_post_ids:
                is_dup = True
                orig_file = seen_post_ids[post.id]
                dup_reason = f"Duplicate post ID encountered: '{post.id}' (already seen as '{orig_file}')"
            elif post.url and post.url in seen_urls:
                is_dup = True
                orig_file = seen_urls[post.url]
                dup_reason = f"Duplicate canonical URL encountered: '{post.url}' (already seen as '{orig_file}')"

            if is_dup:
                report.add_duplicate(
                    post_id=post.id,
                    title=post.title,
                    url=post.url,
                    reason=dup_reason,
                    first_seen_file=orig_file,
                )
                report.add_issue(
                    issue_type="duplicate_post",
                    message=dup_reason,
                    post_id=post.id,
                    post_title=post.title,
                    severity="warning",
                )
                continue

            # 5. Generate unique, collision-resistant filename
            date_prefix = extract_date_prefix(post.published)
            title_slug = slugify(post.title)
            base_filename = f"{date_prefix}-{title_slug}"
            filename = f"{base_filename}.md"

            collision_counter = 2
            while filename in used_filenames:
                filename = f"{base_filename}-{collision_counter}.md"
                collision_counter += 1

            used_filenames.add(filename)
            seen_post_ids[post.id] = filename
            if post.url:
                seen_urls[post.url] = filename

            file_path = self.output_dir / filename

            # 6. Convert content HTML to Markdown with selective HTML preservation
            markdown_body, conv_issues = self.converter.convert(
                raw_html=post.content_html,
                post_id=post.id,
                post_title=post.title,
            )
            for issue in conv_issues:
                report.add_issue(
                    issue_type=issue.issue_type,
                    message=issue.message,
                    post_id=issue.post_id,
                    post_title=issue.post_title,
                    severity=issue.severity,
                )

            # 7. Generate Markdown file with YAML frontmatter classified as personal_analysis
            full_markdown = create_post_markdown_content(
                post=post,
                markdown_body=markdown_body,
                classification=self.classification,
            )

            # 8. Write Markdown file
            if not self.dry_run:
                try:
                    file_path.write_text(full_markdown, encoding="utf-8")
                except Exception as ex:
                    report.add_issue(
                        issue_type="file_write_error",
                        message=f"Failed to write markdown file '{file_path}': {str(ex)}",
                        post_id=post.id,
                        post_title=post.title,
                        severity="error",
                    )
                    continue

            # Record successful conversion
            record = ConvertedPostRecord(
                post_id=post.id,
                title=post.title,
                date=post.published,
                url=post.url,
                labels=post.labels,
                file_path=str(file_path),
                file_name=filename,
                classification=self.classification,
            )
            report.add_converted(record)

        # Verify input file was never modified
        final_hash = compute_file_sha256(feed_file)
        report.input_file_unmodified = initial_hash == final_hash
        if not report.input_file_unmodified:
            report.add_issue(
                issue_type="file_mutation_error",
                message="CRITICAL: Input feed file hash changed during execution! File was unexpectedly modified.",
                severity="error",
            )

        report.duration_seconds = time.time() - start_time

        # Write reports
        if not self.dry_run:
            self.report_json_path.write_text(report.to_json(), encoding="utf-8")
            self.report_md_path.write_text(report.to_markdown(), encoding="utf-8")

        return report
