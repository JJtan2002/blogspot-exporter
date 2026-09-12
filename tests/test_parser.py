"""Unit tests for the Blogger XML parser."""

from pathlib import Path
import pytest

from blogspot_ingestion.parser import BloggerXmlParser, compute_file_sha256

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_XML = FIXTURES_DIR / "sample_blogger_export.xml"


def test_compute_file_sha256():
    hash_val = compute_file_sha256(SAMPLE_XML)
    assert isinstance(hash_val, str)
    assert len(hash_val) == 64


def test_parser_file_not_found():
    with pytest.raises(FileNotFoundError):
        BloggerXmlParser("non_existent_file.xml")


def test_parser_extracts_all_entries():
    parser = BloggerXmlParser(SAMPLE_XML)
    entries = list(parser.parse_entries())

    # 4 published posts + 1 duplicate post + 1 draft + 1 comment + 1 page + 1 template = 9 entries
    assert len(entries) == 9

    kinds = [post.kind for post, _ in entries]
    assert kinds.count("post") == 6
    assert kinds.count("comment") == 1
    assert kinds.count("page") == 1
    assert kinds.count("template") == 1


def test_parser_detects_draft():
    parser = BloggerXmlParser(SAMPLE_XML)
    entries = list(parser.parse_entries())

    drafts = [post for post, _ in entries if post.is_draft]
    assert len(drafts) == 1
    assert drafts[0].title == "Unfinished Thoughts on Quantum Computing"
    assert drafts[0].id == "tag:blogger.com,1999:blog-1234567890123456789.post-9999"


def test_parser_extracts_labels():
    parser = BloggerXmlParser(SAMPLE_XML)
    entries = list(parser.parse_entries())

    first_post = entries[0][0]
    assert first_post.title == "The Evolution of Autonomous Agents"
    assert "Technology" in first_post.labels
    assert "Artificial Intelligence" in first_post.labels

    second_post = entries[1][0]
    assert "Deep Dive" in second_post.labels
    assert "Cloud Computing" in second_post.labels


def test_parser_extracts_canonical_url_and_dates():
    parser = BloggerXmlParser(SAMPLE_XML)
    entries = list(parser.parse_entries())

    first_post = entries[0][0]
    assert first_post.url == "https://tech-analysis.blogspot.com/2025/06/the-evolution-of-autonomous-agents.html"
    assert first_post.published == "2025-06-15T14:30:00.000+08:00"
    assert first_post.updated == "2025-06-16T09:15:00.000+08:00"
    assert first_post.author_name == "Analyst Alex"
