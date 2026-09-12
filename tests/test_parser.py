"""Unit tests for the Blogger XML and Google Takeout Atom parser."""

from pathlib import Path
import pytest

from blogspot_ingestion.parser import (
    BloggerXmlParser,
    compute_file_sha256,
    detect_base_url_from_settings,
    resolve_feed_path,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_XML = FIXTURES_DIR / "sample_blogger_export.xml"
SAMPLE_TAKEOUT = FIXTURES_DIR / "sample_takeout_feed.atom"


def test_compute_file_sha256():
    hash_val = compute_file_sha256(SAMPLE_XML)
    assert isinstance(hash_val, str)
    assert len(hash_val) == 64


def test_parser_file_not_found():
    with pytest.raises(FileNotFoundError):
        BloggerXmlParser("non_existent_file.xml")


def test_resolve_feed_path_directory():
    # Resolving the fixtures directory should locate sample_takeout_feed.atom or sample_blogger_export.xml
    resolved = resolve_feed_path(FIXTURES_DIR)
    assert resolved.is_file()
    assert resolved.suffix in (".atom", ".xml")


def test_detect_base_url_from_settings():
    base_url = detect_base_url_from_settings(SAMPLE_TAKEOUT)
    assert base_url == "https://testjournal.blogspot.com"


def test_legacy_xml_parser_extracts_all_entries():
    parser = BloggerXmlParser(SAMPLE_XML)
    entries = list(parser.parse_entries())

    assert len(entries) == 9
    kinds = [post.kind for post, _ in entries]
    assert kinds.count("post") == 6
    assert kinds.count("comment") == 1
    assert kinds.count("page") == 1
    assert kinds.count("template") == 1


def test_takeout_atom_parser():
    parser = BloggerXmlParser(SAMPLE_TAKEOUT)
    entries = list(parser.parse_entries())

    # 8 total entries in fixture
    assert len(entries) == 8

    posts = [p for p, _ in entries if p.kind == "post"]
    assert len(posts) == 4  # 2 live, 1 trashed, 1 duplicate

    # Check Post 1 metadata and URL construction
    post1 = posts[0]
    assert post1.title == "Decoding Suntec REIT's Earnings Results"
    assert post1.published == "2026-03-01T04:00:00Z"
    assert post1.url == "https://testjournal.blogspot.com/2026/03/decoding-suntec-reits-earnings.html"
    assert "suntec" in post1.labels
    assert "dividend investing" in post1.labels
    assert "reits" in post1.labels
    assert post1.is_draft is False
    assert post1.is_trashed is False

    # Check Draft Page
    draft_pages = [p for p, _ in entries if p.kind == "page" and p.is_draft]
    assert len(draft_pages) == 1
    assert draft_pages[0].title == "Draft Contact Page"

    # Check Live Page
    live_pages = [p for p, _ in entries if p.kind == "page" and not p.is_draft]
    assert len(live_pages) == 1
    assert live_pages[0].title == "Portfolio Overview"

    # Check Comment
    comments = [p for p, _ in entries if p.kind == "comment"]
    assert len(comments) == 1

    # Check Trashed Entry
    trashed = [p for p, _ in entries if p.is_trashed]
    assert len(trashed) == 1
    assert trashed[0].title == "Deleted Test Post"

    # Check unfamiliar entry type issue recording
    unfamiliar = [(p, issues) for p, issues in entries if p.kind == "custom_widget"]
    assert len(unfamiliar) == 1
    p_unfam, p_issues = unfamiliar[0]
    assert any(i.issue_type == "unfamiliar_entry_type" for i in p_issues)
