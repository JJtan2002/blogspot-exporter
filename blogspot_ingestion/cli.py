"""Command-line interface for the Blogger / Blogspot Ingestion Pipeline."""

import argparse
import sys
from pathlib import Path

from blogspot_ingestion.pipeline import IngestionPipeline


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        description="Ingest Blogger/Blogspot Google Takeout (feed.atom/atom.feed) or legacy XML exports into clean Markdown files with YAML frontmatter classified as personal_analysis.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "source",
        type=str,
        help="Path to the Blogger export file (feed.atom, atom.feed, .xml) or export folder",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default="output/posts",
        help="Directory to save generated Markdown files",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Canonical base URL (e.g. https://yourblog.blogspot.com). Auto-detected if settings.csv is found.",
    )
    parser.add_argument(
        "--report-json",
        type=str,
        default=None,
        help="Custom path to save JSON ingestion report (defaults to <output-dir>/../ingestion_report.json)",
    )
    parser.add_argument(
        "--report-md",
        type=str,
        default=None,
        help="Custom path to save Markdown ingestion report (defaults to <output-dir>/../ingestion_report.md)",
    )
    parser.add_argument(
        "--classification",
        type=str,
        default="personal_analysis",
        help="Document classification value in YAML frontmatter",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without writing files to disk (dry run validation)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Display verbose logging output",
    )
    return parser.parse_args(args)


def main(args=None) -> int:
    parsed_args = parse_args(args)
    input_path = Path(parsed_args.source)

    if not input_path.exists():
        print(f"Error: Input path not found: {input_path}", file=sys.stderr)
        return 1

    print("==================================================")
    print("  Blogger / Blogspot Ingestion Pipeline")
    print("==================================================")
    print(f"Source path:       {input_path}")
    print(f"Output directory:  {parsed_args.output_dir}")
    print(f"Classification:    {parsed_args.classification}")
    if parsed_args.base_url:
        print(f"Base URL:          {parsed_args.base_url}")
    print(f"Dry run:           {parsed_args.dry_run}")
    print("--------------------------------------------------")

    try:
        pipeline = IngestionPipeline(
            input_file=input_path,
            output_dir=parsed_args.output_dir,
            report_json_path=parsed_args.report_json,
            report_md_path=parsed_args.report_md,
            classification=parsed_args.classification,
            base_url=parsed_args.base_url,
            dry_run=parsed_args.dry_run,
        )
        report = pipeline.run()

        print("\n--- Ingestion Report Summary ---")
        print(f"Resolved Feed File:          {report.input_file}")
        print(f"Total Feed Entries:          {report.total_entries}")
        print(f"Published Posts Found:       {report.published_posts_found}")
        print(f"Successfully Converted:      {report.converted_count}")
        print(f"Skipped Entries:             {report.skipped_count}")
        for kind, count in sorted(report.skipped_breakdown.items()):
            print(f"  - {kind}: {count}")
        print(f"Duplicate Entries:           {report.duplicate_count}")
        print(f"Issues / Warnings:           {report.issue_count}")
        print(f"Original Archive Unmodified: {'Yes' if report.input_file_unmodified else 'NO (INTEGRITY ERROR)'}")
        print(f"Time Elapsed:                {report.duration_seconds:.3f}s")

        if not parsed_args.dry_run:
            print(f"\nMarkdown files written to:   {report.output_dir}")
            print(f"JSON Report written to:      {pipeline.report_json_path}")
            print(f"Markdown Report written to:  {pipeline.report_md_path}")

        if report.issues and parsed_args.verbose:
            print("\nIssues encountered:")
            for issue in report.issues:
                print(f"  [{issue.severity.upper()}] {issue.issue_type}: {issue.message}")

        if not report.input_file_unmodified:
            print("\nCRITICAL: Input feed archive was modified!", file=sys.stderr)
            return 2

        print("\nIngestion completed successfully.")
        return 0

    except Exception as ex:
        print(f"\nFatal error during pipeline execution: {ex}", file=sys.stderr)
        if parsed_args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
