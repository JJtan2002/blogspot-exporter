"""End-to-end integration tests for the Blogspot Ingestion Pipeline."""

import json
import os
from pathlib import Path
import subprocess
import sys
import yaml

from blogspot_ingestion.parser import compute_file_sha256
from blogspot_ingestion.pipeline import IngestionPipeline

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_XML = FIXTURES_DIR / "sample_blogger_export.xml"


def test_pipeline_end_to_end(tmp_path):
    output_dir = tmp_path / "posts"
    report_json = tmp_path / "ingestion_report.json"
    report_md = tmp_path / "ingestion_report.md"

    # Capture original hash
    original_hash = compute_file_sha256(SAMPLE_XML)

    pipeline = IngestionPipeline(
        input_file=SAMPLE_XML,
        output_dir=output_dir,
        report_json_path=report_json,
        report_md_path=report_md,
        classification="personal_analysis",
    )
    report = pipeline.run()

    # 1. Assert original XML was NOT modified
    after_hash = compute_file_sha256(SAMPLE_XML)
    assert original_hash == after_hash
    assert report.input_file_unmodified is True

    # 2. Check counts in report
    assert report.total_entries == 9
    assert report.published_posts_found == 5  # 4 unique + 1 duplicate
    assert report.converted_count == 4
    assert report.skipped_count == 4  # 1 draft + 1 comment + 1 page + 1 template
    assert report.duplicate_count == 1

    # Check skipped breakdown
    assert report.skipped_breakdown["draft"] == 1
    assert report.skipped_breakdown["comment"] == 1
    assert report.skipped_breakdown["page"] == 1
    assert report.skipped_breakdown["template"] == 1

    # 3. Verify generated files on disk
    generated_files = list(output_dir.glob("*.md"))
    assert len(generated_files) == 4

    # 4. Verify YAML Frontmatter and Content in each file
    for md_file in generated_files:
        content = md_file.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        parts = content.split("---\n")
        assert len(parts) >= 3

        frontmatter_yaml = parts[1]
        body = "---".join(parts[2:]).strip()

        data = yaml.safe_load(frontmatter_yaml)

        # Requirement: classify the document as personal_analysis
        assert data.get("classification") == "personal_analysis"
        assert data.get("type") == "personal_analysis"

        # Requirement: preserve title, publication date, original URL, labels
        assert "title" in data and data["title"]
        assert "date" in data and data["date"]
        assert "url" in data and data["url"].startswith("https://")
        assert "labels" in data and isinstance(data["labels"], list)
        assert "id" in data and data["id"].startswith("tag:blogger.com")

        # Verify content exists in body
        assert len(body) > 0

    # 5. Check specific post content: video embed and complex table preserved in Post 2
    post2_files = [f for f in generated_files if "hardware-benchmarks" in f.name]
    assert len(post2_files) == 1
    post2_content = post2_files[0].read_text(encoding="utf-8")

    # Verify iframe preserved
    assert "<iframe" in post2_content
    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ"' in post2_content

    # Verify complex table with colspan preserved as HTML
    assert "<table" in post2_content
    assert 'colspan="2"' in post2_content

    # Verify simple table was converted to Markdown
    assert "| Device | Throughput (tokens/s) | Latency (ms) |" in post2_content

    # Verify code block converted to fenced markdown with language
    assert "```python" in post2_content
    assert "def calculate_throughput" in post2_content

    # 6. Verify report files were written
    assert report_json.exists()
    assert report_md.exists()

    report_data = json.loads(report_json.read_text(encoding="utf-8"))
    assert report_data["summary"]["converted_count"] == 4
    assert report_data["summary"]["duplicate_count"] == 1
    assert report_data["summary"]["skipped_count"] == 4
    assert report_data["summary"]["input_file_unmodified"] is True

    md_report_content = report_md.read_text(encoding="utf-8")
    assert "# Blogger / Blogspot Ingestion Report" in md_report_content
    assert "Successfully Converted" in md_report_content


def test_pipeline_dry_run(tmp_path):
    output_dir = tmp_path / "posts"
    report_json = tmp_path / "report.json"
    report_md = tmp_path / "report.md"

    pipeline = IngestionPipeline(
        input_file=SAMPLE_XML,
        output_dir=output_dir,
        report_json_path=report_json,
        report_md_path=report_md,
        dry_run=True,
    )
    report = pipeline.run()

    assert report.converted_count == 4
    # Ensure no files were actually written during dry run
    assert not output_dir.exists()
    assert not report_json.exists()
    assert not report_md.exists()


def test_cli_execution(tmp_path):
    output_dir = tmp_path / "cli_posts"
    report_json = tmp_path / "cli_report.json"
    report_md = tmp_path / "cli_report.md"

    cmd = [
        sys.executable,
        "-m",
        "blogspot_ingestion",
        str(SAMPLE_XML),
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
    assert "Successfully Converted:      4" in result.stdout
    assert "Original XML Unmodified:     Yes" in result.stdout

    assert len(list(output_dir.glob("*.md"))) == 4
    assert report_json.exists()
    assert report_md.exists()


def test_filename_collision_resolution(tmp_path):
    xml_content = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom'>
  <id>tag:blogger.com,1999:blog-test</id>
  <entry>
    <id>tag:blogger.com,1999:blog-test.post-1</id>
    <category scheme='http://schemas.google.com/g/2005#kind' term='http://schemas.google.com/blogger/2008/kind#post'/>
    <title type='text'>Duplicate Title</title>
    <published>2025-01-01T10:00:00Z</published>
    <link rel='alternate' type='text/html' href='https://test.blogspot.com/2025/01/p1.html'/>
    <content type='html'>&lt;p&gt;Post 1&lt;/p&gt;</content>
  </entry>
  <entry>
    <id>tag:blogger.com,1999:blog-test.post-2</id>
    <category scheme='http://schemas.google.com/g/2005#kind' term='http://schemas.google.com/blogger/2008/kind#post'/>
    <title type='text'>Duplicate Title</title>
    <published>2025-01-01T11:00:00Z</published>
    <link rel='alternate' type='text/html' href='https://test.blogspot.com/2025/01/p2.html'/>
    <content type='html'>&lt;p&gt;Post 2&lt;/p&gt;</content>
  </entry>
</feed>"""
    test_xml = tmp_path / "collision.xml"
    test_xml.write_text(xml_content, encoding="utf-8")
    out_dir = tmp_path / "collision_out"

    pipeline = IngestionPipeline(test_xml, out_dir)
    report = pipeline.run()

    assert report.converted_count == 2
    filenames = sorted([f.name for f in out_dir.glob("*.md")])
    assert filenames == ["2025-01-01-duplicate-title-2.md", "2025-01-01-duplicate-title.md"]


def test_missing_metadata_issue_tracking(tmp_path):
    xml_content = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom'>
  <id>tag:blogger.com,1999:blog-test</id>
  <entry>
    <category scheme='http://schemas.google.com/g/2005#kind' term='http://schemas.google.com/blogger/2008/kind#post'/>
    <content type='html'>&lt;p&gt;No title, date, id, or url&lt;/p&gt;</content>
  </entry>
</feed>"""
    test_xml = tmp_path / "missing.xml"
    test_xml.write_text(xml_content, encoding="utf-8")
    out_dir = tmp_path / "missing_out"

    pipeline = IngestionPipeline(test_xml, out_dir)
    report = pipeline.run()

    assert report.converted_count == 1
    assert report.issue_count >= 4
    issue_types = [i.issue_type for i in report.issues]
    assert "missing_id" in issue_types
    assert "missing_title" in issue_types
    assert "missing_publication_date" in issue_types
    assert "missing_url" in issue_types


def test_read_only_filesystem_file(tmp_path):
    test_xml = tmp_path / "readonly.xml"
    test_xml.write_text(SAMPLE_XML.read_text(encoding="utf-8"), encoding="utf-8")

    # Mark file read-only
    os.chmod(test_xml, 0o444)

    out_dir = tmp_path / "ro_out"
    pipeline = IngestionPipeline(test_xml, out_dir)
    report = pipeline.run()

    assert report.converted_count == 4
    assert report.input_file_unmodified is True
