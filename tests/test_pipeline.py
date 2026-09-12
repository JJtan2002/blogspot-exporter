"""End-to-end integration tests for the Blogspot Ingestion Pipeline."""

import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
import yaml

from blogspot_ingestion.parser import compute_file_sha256
from blogspot_ingestion.pipeline import IngestionPipeline

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_XML = FIXTURES_DIR / "sample_blogger_export.xml"
SAMPLE_TAKEOUT = FIXTURES_DIR / "sample_takeout_feed.atom"
REAL_TAKEOUT_DIR = Path(__file__).parent.parent / "Blogger"


def test_pipeline_takeout_end_to_end(tmp_path):
    output_dir = tmp_path / "takeout_posts"
    report_json = tmp_path / "takeout_report.json"
    report_md = tmp_path / "takeout_report.md"

    original_hash = compute_file_sha256(SAMPLE_TAKEOUT)

    pipeline = IngestionPipeline(
        input_file=SAMPLE_TAKEOUT,
        output_dir=output_dir,
        report_json_path=report_json,
        report_md_path=report_md,
        classification="personal_analysis",
    )
    report = pipeline.run()

    # 1. Assert input file hash was strictly preserved
    after_hash = compute_file_sha256(SAMPLE_TAKEOUT)
    assert original_hash == after_hash
    assert report.input_file_unmodified is True

    # 2. Check counts: 8 total entries in fixture
    # - 2 published posts
    # - 1 duplicate post
    # - 1 draft page
    # - 1 live page
    # - 1 comment
    # - 1 trashed post
    # - 1 unfamiliar custom_widget
    assert report.total_entries == 8
    assert report.published_posts_found == 3  # 2 unique + 1 duplicate
    assert report.converted_count == 2
    assert report.skipped_count == 5
    assert report.duplicate_count == 1

    # Check skipped breakdown
    assert report.skipped_breakdown.get("page") == 2  # 1 live page, 1 draft page
    assert report.skipped_breakdown.get("comment") == 1
    assert report.skipped_breakdown.get("trashed") == 1
    assert report.skipped_breakdown.get("custom_widget") == 1

    # Check unfamiliar entry issue was recorded
    assert any(i.issue_type == "unfamiliar_entry_type" for i in report.issues)

    # 3. Check generated files
    files = list(output_dir.glob("*.md"))
    assert len(files) == 2

    # Verify frontmatter in converted posts
    for f in files:
        text = f.read_text(encoding="utf-8")
        parts = text.split("---\n")
        assert len(parts) >= 3
        fm = yaml.safe_load(parts[1])
        assert fm["classification"] == "personal_analysis"
        assert fm["type"] == "personal_analysis"
        assert fm["title"]
        assert fm["date"]
        assert fm["url"].startswith("https://testjournal.blogspot.com/")
        assert isinstance(fm["labels"], list)

    # Check Post 2 table conversion and caption conversion
    post2_files = [f for f in files if "portfolio-update" in f.name]
    assert len(post2_files) == 1
    post2_md = post2_files[0].read_text(encoding="utf-8")
    assert "| Status | Date | Stock / REIT |" in post2_md
    assert "| Received | 16 Feb 2026 | Kimly |" in post2_md
    assert "*Historical payout chart*" in post2_md


def test_pipeline_legacy_xml_end_to_end(tmp_path):
    output_dir = tmp_path / "legacy_posts"
    report_json = tmp_path / "legacy_report.json"
    report_md = tmp_path / "legacy_report.md"

    original_hash = compute_file_sha256(SAMPLE_XML)

    pipeline = IngestionPipeline(
        input_file=SAMPLE_XML,
        output_dir=output_dir,
        report_json_path=report_json,
        report_md_path=report_md,
        classification="personal_analysis",
    )
    report = pipeline.run()

    after_hash = compute_file_sha256(SAMPLE_XML)
    assert original_hash == after_hash
    assert report.input_file_unmodified is True

    assert report.total_entries == 9
    assert report.published_posts_found == 5
    assert report.converted_count == 4
    assert report.skipped_count == 4
    assert report.duplicate_count == 1


def test_directory_input_resolution(tmp_path):
    output_dir = tmp_path / "dir_posts"

    # Passing FIXTURES_DIR directly should resolve the feed file
    pipeline = IngestionPipeline(
        input_file=FIXTURES_DIR,
        output_dir=output_dir,
        dry_run=True,
    )
    report = pipeline.run()
    assert report.converted_count > 0


def test_cli_execution_with_takeout_atom(tmp_path):
    output_dir = tmp_path / "cli_takeout_posts"
    report_json = tmp_path / "cli_takeout_report.json"
    report_md = tmp_path / "cli_takeout_report.md"

    cmd = [
        sys.executable,
        "-m",
        "blogspot_ingestion",
        str(SAMPLE_TAKEOUT),
        "-o",
        str(output_dir),
        "--report-json",
        str(report_json),
        "--report-md",
        str(report_md),
        "--verbose",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0
    assert "Successfully Converted:      2" in result.stdout
    assert "Original Archive Unmodified: Yes" in result.stdout
    assert len(list(output_dir.glob("*.md"))) == 2


@pytest.mark.skipif(not REAL_TAKEOUT_DIR.exists(), reason="User Blogger Takeout export directory not present")
def test_real_takeout_export_fidelity(tmp_path):
    output_dir = tmp_path / "real_posts"
    pipeline = IngestionPipeline(
        input_file=REAL_TAKEOUT_DIR,
        output_dir=output_dir,
    )
    report = pipeline.run()

    # Verify counts against actual user Takeout export
    assert report.total_entries == 91
    assert report.published_posts_found == 82
    assert report.converted_count == 82
    assert report.skipped_count == 9  # 7 comments + 2 pages
    assert report.duplicate_count == 0
    assert report.input_file_unmodified is True

    # Verify converted files
    generated = list(output_dir.glob("*.md"))
    assert len(generated) == 82

    # Spot-check specific known posts for content fidelity
    suntec_file = next(f for f in generated if "decoding-suntec-reits-fy2025" in f.name)
    suntec_text = suntec_file.read_text(encoding="utf-8")
    assert "Suntec REIT" in suntec_text
    assert "decoding-suntec-reits-fy2025-earnings.html" in suntec_text

    portfolio_q1_file = next(f for f in generated if "portfolio-update-q1-2026" in f.name)
    portfolio_q1_text = portfolio_q1_file.read_text(encoding="utf-8")
    # Verify table integrity
    assert "| **Status** | **Date** | **Stock / REIT** |" in portfolio_q1_text
    assert "| ✅ **Received** | 16 Feb 2026 | Kimly |" in portfolio_q1_text
    assert "| ✅ **Received** | 25 Feb 2026 | SGX |" in portfolio_q1_text
    assert "| ⏳ **Upcoming** | 17 Apr 2026 | DBS |" in portfolio_q1_text
