# Blogspot Exporter & Ingestion Pipeline

A robust, read-only Python pipeline for converting Blogger/Blogspot Atom XML export archives into clean, structured Markdown files with standardized YAML frontmatter.

---

## 1. What the Project Does

When exporting a blog from Blogger/Blogspot, Google provides a single large Atom XML feed containing all historical posts, drafts, comments, pages, and template settings.

This pipeline:
- **Parses Blogger XML archives without modifying them** (verified with SHA-256 integrity checks before and after execution).
- **Extracts published posts** while cleanly filtering out drafts (`<app:control><app:draft>yes</app:draft></app:control>`), comments, static pages, and layout templates.
- **Converts post content from HTML to clean Markdown**, preserving rich elements only when they cannot be represented in standard Markdown (e.g. YouTube `<iframe>` embeds, `<video>`, `<audio>`, `<details>`, and complex `<table>` grids with `colspan`/`rowspan`).
- **Injects standardized YAML frontmatter** into every post, classifying each document as `personal_analysis` and preserving title, publication date, canonical URL, tags/labels, and unique post IDs.
- **Identifies and skips duplicate entries** (by post ID and canonical URL) to prevent collisions.
- **Generates comprehensive ingestion reports** (both Markdown and JSON) tracking converted files, skipped entries with category breakdowns, detected duplicates, and conversion warnings.

---

## 2. Current Project Status

- **Status**: Stable baseline implementation.
- **Test Coverage**: 19 automated unit and integration tests passing (`pytest`).
- **Platform Support**: Cross-platform (tested on Windows 11 with PowerShell, compatible with Linux/macOS).

---

## 3. High-Level Architecture & Components

The pipeline is organized into modular single-responsibility components:

```
+-----------------------------------------------------------+
|               Blogger XML Export (.xml)                   | (Read-only input)
+-----------------------------+-----------------------------+
                              |
                              v
                +----------------------------+
                | BloggerXmlParser (parser)  |
                +--------------+-------------+
                               |
            +------------------+------------------+
            |                                     |
            v                                     v
   [Published Posts]                    [Filtered Entries]
            |                            - Drafts (<app:draft>)
            v                            - Comments (#comment)
   [Deduplication Index]                 - Static Pages (#page)
   - Checks Seen Post IDs & URLs         - Templates (#template)
            |
            v
  +--------------------------------+
  | ContentConverter (converter)   |
  +----------------+---------------+
                   | - Headings, paragraphs, lists, bold/italics -> Markdown
                   | - iframes, complex tables, audio/video -> preserved HTML
                   v
  +--------------------------------+
  | Frontmatter Builder            | -> Injects YAML frontmatter:
  +----------------+---------------+    classification: personal_analysis
                   |
                   v
  +--------------------------------+
  | File Writer & Collision Guard  | -> output/posts/YYYY-MM-DD-<slug>.md
  +----------------+---------------+
                   |
                   v
  +--------------------------------+
  | Ingestion Report Generator     | -> output/ingestion_report.md
  +--------------------------------+    output/ingestion_report.json
```

- **`blogspot_ingestion/parser.py`**: Reads the XML archive using `xml.etree.ElementTree`, inspects Atom namespaces, extracts metadata, identifies entry types, and computes SHA-256 integrity hashes.
- **`blogspot_ingestion/converter.py`**: Subclasses `markdownify.MarkdownConverter` alongside `BeautifulSoup` to transform HTML into clean Markdown while preserving HTML embeds and complex tables.
- **`blogspot_ingestion/frontmatter.py`**: Uses `PyYAML` to format and validate metadata frontmatter delimited by `---`.
- **`blogspot_ingestion/pipeline.py`**: Coordinates parsing, deduplication, slug generation, collision handling, file output, and report compilation.
- **`blogspot_ingestion/models.py`**: Dataclasses for posts, issues, skipped items, duplicates, and report summaries.
- **`blogspot_ingestion/cli.py`**: Command-line interface with options for output paths, report formats, dry-run mode, and verbosity.

---

## 4. Repository Structure

```text
blogging/
├── .env.example                     # Optional configuration template
├── .gitignore                       # Git exclusion rules
├── AGENTS.md                        # Research & editorial guidelines
├── README.md                        # Project documentation (this file)
├── requirements.txt                 # Pinned Python package dependencies
├── blogspot_ingestion/              # Main Python package
│   ├── __init__.py                  # Package exports
│   ├── __main__.py                  # Entrypoint for python -m execution
│   ├── cli.py                       # CLI argument parsing and execution
│   ├── converter.py                 # HTML-to-Markdown conversion engine
│   ├── frontmatter.py               # YAML frontmatter builder
│   ├── models.py                    # Data classes and report data structures
│   ├── parser.py                    # Atom XML feed parser and hasher
│   └── pipeline.py                  # Core pipeline orchestrator
└── tests/                           # Test suite
    ├── fixtures/
    │   └── sample_blogger_export.xml# Test fixture representing Blogger Atom feed
    ├── test_converter.py            # Unit tests for HTML/Markdown conversion
    ├── test_parser.py               # Unit tests for XML parsing & metadata
    └── test_pipeline.py             # Integration tests, CLI tests, and edge cases
```

*Note: Generated output directories (`output/`) and local Python virtual environments (`.venv/`) are excluded from version control.*

---

## 5. Prerequisites

- **Python**: 3.10 or higher (tested on Python 3.13)
- **Git**: 2.30 or higher

---

## 6. Environment Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/<username>/<repo-name>.git
   cd blogging
   ```

2. **Create and activate a virtual environment**:
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

## 7. How to Run the Project

### Basic Ingestion Workflow

To ingest a Blogger XML export file into Markdown posts:

```powershell
python -m blogspot_ingestion path/to/your_blogger_export.xml -o output/posts
```

### Dry-Run Validation Workflow

To parse and validate an export file without writing any files to disk:

```powershell
python -m blogspot_ingestion path/to/your_blogger_export.xml --dry-run
```

### Custom Classification and Output Paths

```powershell
python -m blogspot_ingestion path/to/export.xml `
  -o output/custom_posts `
  --report-json output/reports/summary.json `
  --report-md output/reports/summary.md `
  --classification personal_analysis `
  --verbose
```

### CLI Command Options

| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `xml_file` | Positional | *(Required)* | Path to Blogger/Blogspot XML export file |
| `-o`, `--output-dir` | Flag | `output/posts` | Directory to save generated Markdown files |
| `--report-json` | Flag | `<out>/../ingestion_report.json` | Path to save JSON ingestion report |
| `--report-md` | Flag | `<out>/../ingestion_report.md` | Path to save Markdown ingestion report |
| `--classification` | Flag | `personal_analysis` | Document classification in YAML frontmatter |
| `--dry-run` | Flag | `False` | Run parsing and validation without writing files |
| `-v`, `--verbose` | Flag | `False` | Print detailed logs during execution |

---

## 8. Python API Workflow

You can also integrate the pipeline directly into Python scripts or larger data pipelines:

```python
from pathlib import Path
from blogspot_ingestion import IngestionPipeline

pipeline = IngestionPipeline(
    input_file=Path("path/to/blogger_export.xml"),
    output_dir=Path("output/posts"),
    classification="personal_analysis",
)

report = pipeline.run()

print(f"Total entries:      {report.total_entries}")
print(f"Converted posts:    {report.converted_count}")
print(f"Skipped entries:    {report.skipped_count}")
print(f"Duplicates:         {report.duplicate_count}")
print(f"Source unmodified:  {report.input_file_unmodified}")
```

---

## 9. Running Tests

The test suite validates HTML conversions, complex table handling, iframe preservation, language detection in code blocks, draft detection, collision handling, and file integrity:

```powershell
python -m pytest -v
```

---

## 10. Configuration & Environment Variables

This pipeline operates completely locally and requires **no external API keys, cloud tokens, or database credentials**.

An optional `.env.example` file is provided for developers who wish to set default paths when extending the project:

- `BLOGSPOT_EXPORT_PATH`: Default path to input XML archive.
- `BLOGSPOT_OUTPUT_DIR`: Default directory for output Markdown files.
- `DEFAULT_CLASSIFICATION`: Default document classification value.

---

## 11. Current Limitations & Known Issues

- **Export Archive Scope**: Designed specifically for Blogger/Blogspot Atom XML feed exports (the standard file generated via Blogger *Settings > Manage Blog > Back up content*). It does not fetch posts over HTTP via the Google Blogger API v3.
- **Embedded External Assets**: Images hosted on Google User Content (`blogger.googleusercontent.com` / `bp.blogspot.com`) or third-party servers remain linked via their remote URLs; images are not currently downloaded or cached locally to an assets folder.
- **Custom Blogspot Widgets**: Arbitrary proprietary third-party JavaScript widgets (such as legacy Flash widgets or dynamic visitor counters) are preserved as raw HTML if present in post bodies, which may render inert in static Markdown viewers.

---

## 12. Intended Future Direction

- **Local Asset Ingestion**: Adding an optional `--download-images` flag to mirror remote image assets locally and rewrite image links to relative paths (`./assets/...`).
- **Direct Second Brain / RAG Ingestion**: Interfacing directly with downstream knowledge stores, vector embeddings, and full-text search indexes.
- **Cross-linking & Metadata Extraction**: Automatically linking mentioned ticker symbols (e.g. SGX tickers) and financial reports to related research documents.
