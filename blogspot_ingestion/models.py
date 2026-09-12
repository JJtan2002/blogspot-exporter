"""Data models for the Blogspot Ingestion Pipeline."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import json


@dataclass
class BlogPost:
    """Represents an extracted Blogger/Blogspot entry."""
    id: str
    title: str
    published: str
    updated: Optional[str] = None
    url: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    content_html: str = ""
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    is_draft: bool = False
    kind: str = "post"
    entry_index: int = 0


@dataclass
class IngestionIssue:
    """Records any warning or issue encountered during parsing or conversion."""
    issue_type: str
    message: str
    post_id: Optional[str] = None
    post_title: Optional[str] = None
    severity: str = "warning"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "issue_type": self.issue_type,
            "post_id": self.post_id,
            "post_title": self.post_title,
            "message": self.message,
        }


@dataclass
class DuplicateEntry:
    """Records information about an identified duplicate entry."""
    post_id: str
    title: str
    url: Optional[str]
    reason: str
    first_seen_file: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "post_id": self.post_id,
            "title": self.title,
            "url": self.url,
            "reason": self.reason,
            "first_seen_file": self.first_seen_file,
        }


@dataclass
class SkippedEntry:
    """Records an entry that was intentionally skipped (draft, comment, page, template, etc.)."""
    post_id: str
    title: str
    kind: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "post_id": self.post_id,
            "title": self.title,
            "kind": self.kind,
            "reason": self.reason,
        }


@dataclass
class ConvertedPostRecord:
    """Records metadata of a successfully written Markdown file."""
    post_id: str
    title: str
    date: str
    url: Optional[str]
    labels: List[str]
    file_path: str
    file_name: str
    classification: str = "personal_analysis"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "post_id": self.post_id,
            "title": self.title,
            "date": self.date,
            "url": self.url,
            "labels": self.labels,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "classification": self.classification,
        }


@dataclass
class IngestionReport:
    """Comprehensive report summarizing the results of the ingestion process."""
    input_file: str
    output_dir: str
    total_entries: int = 0
    published_posts_found: int = 0
    converted_count: int = 0
    skipped_count: int = 0
    skipped_breakdown: Dict[str, int] = field(default_factory=dict)
    duplicate_count: int = 0
    issue_count: int = 0
    converted_posts: List[ConvertedPostRecord] = field(default_factory=list)
    skipped_entries: List[SkippedEntry] = field(default_factory=list)
    duplicates: List[DuplicateEntry] = field(default_factory=list)
    issues: List[IngestionIssue] = field(default_factory=list)
    input_file_hash_sha256: Optional[str] = None
    input_file_unmodified: bool = True
    duration_seconds: float = 0.0

    def add_issue(
        self,
        issue_type: str,
        message: str,
        post_id: Optional[str] = None,
        post_title: Optional[str] = None,
        severity: str = "warning",
    ) -> None:
        self.issues.append(
            IngestionIssue(
                issue_type=issue_type,
                message=message,
                post_id=post_id,
                post_title=post_title,
                severity=severity,
            )
        )
        self.issue_count = len(self.issues)

    def add_duplicate(
        self,
        post_id: str,
        title: str,
        url: Optional[str],
        reason: str,
        first_seen_file: Optional[str] = None,
    ) -> None:
        self.duplicates.append(
            DuplicateEntry(
                post_id=post_id,
                title=title,
                url=url,
                reason=reason,
                first_seen_file=first_seen_file,
            )
        )
        self.duplicate_count = len(self.duplicates)

    def add_skipped(self, post_id: str, title: str, kind: str, reason: str) -> None:
        self.skipped_entries.append(
            SkippedEntry(post_id=post_id, title=title, kind=kind, reason=reason)
        )
        self.skipped_count = len(self.skipped_entries)
        self.skipped_breakdown[kind] = self.skipped_breakdown.get(kind, 0) + 1

    def add_converted(self, record: ConvertedPostRecord) -> None:
        self.converted_posts.append(record)
        self.converted_count = len(self.converted_posts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": {
                "input_file": self.input_file,
                "output_dir": self.output_dir,
                "input_file_hash_sha256": self.input_file_hash_sha256,
                "input_file_unmodified": self.input_file_unmodified,
                "total_entries": self.total_entries,
                "published_posts_found": self.published_posts_found,
                "converted_count": self.converted_count,
                "skipped_count": self.skipped_count,
                "skipped_breakdown": self.skipped_breakdown,
                "duplicate_count": self.duplicate_count,
                "issue_count": self.issue_count,
                "duration_seconds": round(self.duration_seconds, 3),
            },
            "converted_posts": [c.to_dict() for c in self.converted_posts],
            "skipped_entries": [s.to_dict() for s in self.skipped_entries],
            "duplicates": [d.to_dict() for d in self.duplicates],
            "issues": [i.to_dict() for i in self.issues],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines = [
            "# Blogger / Blogspot Ingestion Report",
            "",
            f"**Generated on:** {datetime.now().isoformat()}",
            f"**Input File:** `{self.input_file}`",
            f"**Output Directory:** `{self.output_dir}`",
            f"**Execution Duration:** {self.duration_seconds:.2f}s",
            f"**Original XML Unmodified:** {'✅ Yes' if self.input_file_unmodified else '❌ No'}",
            "",
            "## Summary Metrics",
            "",
            "| Metric | Count |",
            "| :--- | :--- |",
            f"| **Total XML Entries** | {self.total_entries} |",
            f"| **Published Posts Found** | {self.published_posts_found} |",
            f"| **Successfully Converted** | {self.converted_count} |",
            f"| **Skipped Entries** | {self.skipped_count} |",
            f"| **Duplicate Entries** | {self.duplicate_count} |",
            f"| **Conversion Issues / Warnings** | {self.issue_count} |",
            "",
        ]

        if self.skipped_breakdown:
            lines.extend([
                "### Skipped Entries Breakdown",
                "",
                "| Category | Count |",
                "| :--- | :--- |",
            ])
            for kind, count in sorted(self.skipped_breakdown.items()):
                lines.append(f"| {kind.capitalize()} | {count} |")
            lines.append("")

        if self.duplicates:
            lines.extend([
                "## Duplicates Detected",
                "",
                "| Title | Post ID | Reason |",
                "| :--- | :--- | :--- |",
            ])
            for d in self.duplicates:
                escaped_title = d.title.replace("|", "\\|")
                lines.append(f"| {escaped_title} | `{d.post_id}` | {d.reason} |")
            lines.append("")

        if self.issues:
            lines.extend([
                "## Conversion Issues & Warnings",
                "",
                "| Severity | Issue Type | Post / Title | Details |",
                "| :--- | :--- | :--- | :--- |",
            ])
            for issue in self.issues:
                title_or_id = issue.post_title or issue.post_id or "N/A"
                title_or_id = title_or_id.replace("|", "\\|")
                msg = issue.message.replace("|", "\\|")
                lines.append(
                    f"| {issue.severity.upper()} | `{issue.issue_type}` | {title_or_id} | {msg} |"
                )
            lines.append("")

        lines.extend([
            "## Converted Posts",
            "",
            "| Date | Title | Output File | Labels |",
            "| :--- | :--- | :--- | :--- |",
        ])
        for p in self.converted_posts:
            clean_title = p.title.replace("|", "\\|")
            labels_str = ", ".join(p.labels) if p.labels else "-"
            lines.append(f"| {p.date[:10]} | {clean_title} | `{p.file_name}` | {labels_str} |")
        lines.append("")

        return "\n".join(lines)
