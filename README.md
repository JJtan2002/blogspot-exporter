# Blogspot Exporter & Ingestion Pipeline

A robust, read-only Python pipeline for ingesting Blogger/Blogspot blog data exported via **Google Takeout** and converting it into clean, structured Markdown files with standardized YAML frontmatter.

---

## 1. Google Takeout & Blogger Export Workflow

Modern Blogger/Blogspot backups are provided through **Google Takeout** rather than the legacy in-dashboard XML backup.

### Obtaining the Export from Google Takeout
1. Navigate to [Google Takeout](https://takeout.google.com/).
2. Deselect all services and select **Blogger**.
3. Create and download the export archive (`.zip`).
4. Extract the archive into your workspace or project root.

The extracted Google Takeout archive contains a `Blogger/` directory with:
- **`Blogger/Blogs/<Blog Name>/feed.atom`** (or `atom.feed`): The complete Atom 1.0 feed containing all blog posts, pages, comments, and metadata.
- **`Blogger/Blogs/<Blog Name>/settings.csv`**: Blog settings (including subdomain, blog title, and publishing mode) used by the pipeline to automatically reconstruct canonical post URLs.
- **`Blogger/Comments/`**: Comment export feeds.
- **`Blogger/Albums/`**: Uploaded post image assets.

The pipeline accepts the extracted `Blogger` directory, the blog folder (`Blogger/Blogs/<Blog Name>`), or the direct `feed.atom` / `atom.feed` file.

---

## 2. What the Project Does

The ingestion pipeline executes the following workflow:

```
Google Takeout (feed.atom / atom.feed)
                   ↓
         Parse Blogger entries
                   ↓
      Identify published posts
  (filter drafts, pages, comments, trashed)
                   ↓
        Extract post metadata
  (title, date, canonical URL, tags, ID)
                   ↓
      Convert HTML → Markdown
 (selective preservation of iframes & tables)
                   ↓
  Write Markdown + YAML frontmatter
    (classification: personal_analysis)
                   ↓
     Generate Ingestion Report
```

- **Read-Only Ingestion**: Operates strictly read-only on the source archive; verifies data integrity with SHA-256 hashing before and after execution.
- **Selective HTML Preservation**: Converts standard formatting (headings, paragraphs, lists, bold/italics, quotes, code blocks, images) to clean Markdown, while preserving elements that cannot be cleanly expressed in Markdown (e.g. YouTube `<iframe>` embeds, `<video>`, `<audio>`, `<details>`, and complex `<table>` grids with `colspan`/`rowspan`).
- **Standardized YAML Frontmatter**: Classifies each document as `personal_analysis` (`classification: personal_analysis` and `type: personal_analysis`) and preserves publication dates, canonical URLs, and labels.
- **Deduplication & Collision Guard**: Detects and skips duplicated entries, generating collision-resistant filenames (`YYYY-MM-DD-<slug>.md`).
- **Conversion Reporting**: Summarizes total entries, successfully converted posts, skipped categories, and any conversion issues in both Markdown (`ingestion_report.md`) and JSON (`ingestion_report.json`).

---

## 3. Supported & Filtered Blogger Entry Types

Google Takeout exports contain multiple entry types and lifecycle states. The pipeline explicitly distinguishes between them:

| Entry Type | Status in Takeout Feed | Pipeline Action | Description / Handling |
| :--- | :--- | :--- | :--- |
| **Published Post** | `<type>POST</type>` + `<status>LIVE</status>` | **Converted** | Standard blog post; converted to standalone Markdown file with YAML frontmatter. |
| **Draft Post** | `<type>POST</type>` + `<status>DRAFT</status>` (or `<app:draft>yes</app:draft>`) | **Skipped** | Unpublished work-in-progress; recorded in skipped summary under `draft`. |
| **Static Page** | `<type>PAGE</type>` (`LIVE` or `DRAFT`) | **Skipped** | Standalone blog page (e.g. *About*, *Contact*, *Portfolio*); recorded in skipped summary under `page`. |
| **Comment** | `<type>COMMENT</type>` (or `<inReplyTo>` / `in-reply-to`) | **Skipped** | Reader comment on a blog post; recorded in skipped summary under `comment`. |
| **Trashed Entry** | `<status>TRASHED</status>` or non-empty `<trashed>` | **Skipped** | Deleted item; recorded in skipped summary under `trashed`. |
| **Templates / Settings** | `<type>TEMPLATE</type>`, `theme-layouts.xml` | **Skipped** | Blog theme configuration; recorded in skipped summary under `template`. |
| **Duplicates** | Identical `post_id` or canonical `url` | **Skipped** | Duplicate entry; recorded in report with reference to the original file. |
| **Unfamiliar Types** | Any unmapped entry type | **Skipped** | Flagged with a warning in `ingestion_report.json` so no entries are silently lost. |

---

## 4. Current Project Status

- **Status**: Stable, tested with real-world Google Takeout archives and legacy Blogger XML backups.
- **Test Coverage**: 20 automated unit and integration tests passing (`pytest`).
- **Platform**: Cross-platform (Windows PowerShell, macOS, Linux).

---

## 5. Repository Structure

```text
blogging/
├── .env.example                     # Optional configuration template
├── .gitignore                       # Git exclusion rules
├── README.md                        # Project documentation (this file)
├── requirements.txt                 # Pinned Python dependencies
├── blogspot_ingestion/              # Main Python package
│   ├── __init__.py                  # Package exports
│   ├── __main__.py                  # Entrypoint for python -m execution
│   ├── cli.py                       # Command-line interface
│   ├── converter.py                 # HTML-to-Markdown engine with selective preservation
│   ├── frontmatter.py               # YAML frontmatter builder
│   ├── models.py                    # Data classes and report structures
│   ├── parser.py                    # Google Takeout Atom & XML feed parser
│   └── pipeline.py                  # Ingestion pipeline orchestrator
└── tests/                           # Test suite
    ├── fixtures/
    │   ├── sample_takeout_feed.atom # Google Takeout Atom test fixture
    │   ├── sample_blogger_export.xml# Legacy Blogger XML test fixture
    │   └── settings.csv             # Test blog settings fixture
    ├── test_converter.py            # Unit tests for HTML/Markdown conversion
    ├── test_parser.py               # Unit tests for parser and metadata extraction
    └── test_pipeline.py             # Integration tests and real Takeout fidelity tests
```

---

## 6. Prerequisites & Setup

1. **Prerequisites**: Python 3.10+ (tested on Python 3.13) and Git.
2. **Create and activate virtual environment**:
   - **Windows (PowerShell)**:
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 7. How to Run the Importer

### Recommended: Ingest directly from the Google Takeout folder

Extract your Google Takeout archive into the project (e.g. `Blogger/`). Then run:

```powershell
python -m blogspot_ingestion Blogger -o output/posts
```

The pipeline automatically locates `Blogger/Blogs/<Blog Name>/feed.atom` and reads `settings.csv` to reconstruct full canonical post URLs (e.g. `https://yourblog.blogspot.com/2026/03/post-slug.html`).

### Ingesting an explicit feed file

You can also point directly to any `feed.atom` or `atom.feed` file:

```powershell
python -m blogspot_ingestion path/to/feed.atom -o output/posts
```

### Dry-run validation

To inspect entry counts and validate conversion without writing files to disk:

```powershell
python -m blogspot_ingestion Blogger --dry-run
```

### Specifying a custom Base URL

If `settings.csv` is not present, you can supply your blog's base URL explicitly:

```powershell
python -m blogspot_ingestion path/to/feed.atom -o output/posts --base-url https://myblog.blogspot.com
```

### CLI Options Summary

| Flag | Default | Description |
| :--- | :--- | :--- |
| `source` | *(Required)* | Path to Takeout folder (`Blogger`), blog folder, or direct feed file (`feed.atom`, `atom.feed`, `.xml`) |
| `-o`, `--output-dir` | `output/posts` | Directory to save generated Markdown files |
| `--base-url` | *Auto-detected* | Base URL (e.g. `https://blogname.blogspot.com`). Auto-detected from `settings.csv` if available |
| `--report-json` | `<out>/../ingestion_report.json` | Path for JSON conversion report |
| `--report-md` | `<out>/../ingestion_report.md` | Path for Markdown summary report |
| `--classification` | `personal_analysis` | Document classification string in YAML frontmatter |
| `--dry-run` | `False` | Run parsing and validation without writing files |
| `-v`, `--verbose` | `False` | Print detailed logs |

---

## 8. Output Format

For each published post, the pipeline writes a Markdown file named `YYYY-MM-DD-<slug>.md` into the output directory.

### Example Markdown Output

```markdown
---
title: Sample Ingested Blog Post Title
date: '2026-03-01T04:00:00Z'
url: https://myblog.blogspot.com/2026/03/sample-post.html
labels:
- technology
- analysis
classification: personal_analysis
type: personal_analysis
id: tag:blogger.com,1999:blog-9876543210987654321.post-1001
updated: '2026-03-02T08:00:00Z'
author: Blog Author
---

### Key Earnings Metrics

Suntec REIT announced its latest results, showing **resilient distribution per unit**.

- Portfolio occupancy remains above 95%
- Gearing ratio stabilized near 42%

Read more on [SGX announcements](https://example.com/suntec).
```

### Ingestion Summary Reports

The pipeline generates both `ingestion_report.md` and `ingestion_report.json` summarizing:
- Total feed entries processed
- Successfully converted posts
- Categorized breakdown of skipped entries (`draft`, `page`, `comment`, `trashed`)
- Detected duplicates
- Verification that the input archive was never modified (SHA-256 hash match)

---

## 9. Running Tests

```powershell
python -m pytest -v
```
