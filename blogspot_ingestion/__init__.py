"""Blogger / Blogspot Ingestion Pipeline package."""

from blogspot_ingestion.converter import BloggerMarkdownConverter, ContentConverter, is_complex_table
from blogspot_ingestion.frontmatter import (
    build_frontmatter_data,
    create_post_markdown_content,
    dump_yaml_frontmatter,
)
from blogspot_ingestion.models import (
    BlogPost,
    ConvertedPostRecord,
    DuplicateEntry,
    IngestionIssue,
    IngestionReport,
    SkippedEntry,
)
from blogspot_ingestion.parser import BloggerXmlParser, compute_file_sha256
from blogspot_ingestion.pipeline import IngestionPipeline, extract_date_prefix, slugify

__version__ = "1.0.0"

__all__ = [
    "BloggerMarkdownConverter",
    "BloggerXmlParser",
    "BlogPost",
    "ContentConverter",
    "ConvertedPostRecord",
    "DuplicateEntry",
    "IngestionIssue",
    "IngestionPipeline",
    "IngestionReport",
    "SkippedEntry",
    "build_frontmatter_data",
    "compute_file_sha256",
    "create_post_markdown_content",
    "dump_yaml_frontmatter",
    "extract_date_prefix",
    "is_complex_table",
    "slugify",
]
