"""Unit tests for HTML-to-Markdown conversion with selective HTML preservation."""

import pytest
from bs4 import BeautifulSoup
from blogspot_ingestion.converter import ContentConverter, is_complex_table


@pytest.fixture
def converter():
    return ContentConverter()


def test_standard_markdown_conversion(converter):
    raw_html = """
    <h2>Heading Level 2</h2>
    <p>This is a <strong>bold</strong> and <em>italic</em> sentence with a <a href="https://example.com">link</a>.</p>
    <ul>
      <li>First item</li>
      <li>Second item</li>
    </ul>
    <blockquote><p>Wise quotation.</p></blockquote>
    """
    md, issues = converter.convert(raw_html)
    assert not issues
    assert "## Heading Level 2" in md
    assert "**bold**" in md
    assert "*italic*" in md
    assert "[link](https://example.com)" in md
    assert "- First item" in md
    assert "- Second item" in md
    assert "> Wise quotation." in md


def test_preserves_iframe_embeds(converter):
    raw_html = """
    <p>Check out the live recording:</p>
    <iframe width="560" height="315" src="https://www.youtube.com/embed/dQw4w9WgXcQ" title="Demo" frameborder="0" allowfullscreen="allowfullscreen"></iframe>
    <p>End of section.</p>
    """
    md, issues = converter.convert(raw_html)
    assert not issues
    assert "<iframe" in md
    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ"' in md
    assert "</iframe>" in md


def test_converts_simple_table_to_markdown_table(converter):
    raw_html = """
    <table>
      <thead>
        <tr><th>Language</th><th>Typing</th></tr>
      </thead>
      <tbody>
        <tr><td>Python</td><td>Dynamic</td></tr>
        <tr><td>Rust</td><td>Static</td></tr>
      </tbody>
    </table>
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    table_el = soup.find("table")
    assert not is_complex_table(table_el)

    md, issues = converter.convert(raw_html)
    assert not issues
    assert "| Language | Typing |" in md
    assert "| --- | --- |" in md
    assert "| Python | Dynamic |" in md
    assert "| Rust | Static |" in md
    assert "<table" not in md


def test_preserves_complex_table_with_colspan_as_html(converter):
    raw_html = """
    <table border="1">
      <tr>
        <th colspan="2">Cluster Group</th>
        <th>Cost</th>
      </tr>
      <tr>
        <td>Node 1</td>
        <td>Node 2</td>
        <td>$10</td>
      </tr>
    </table>
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    table_el = soup.find("table")
    assert is_complex_table(table_el)

    md, issues = converter.convert(raw_html)
    assert not issues
    assert "<table" in md
    assert 'colspan="2"' in md
    assert "Cluster Group" in md
    assert "</table>" in md


def test_preserves_multimedia_and_details(converter):
    raw_html = """
    <video controls width="250"><source src="/video.mp4" type="video/mp4"></video>
    <audio controls src="/sound.mp3"></audio>
    <details>
      <summary>Click to expand technical breakdown</summary>
      <p>Hidden details here.</p>
    </details>
    <p>Chemical: H<sub>2</sub>O and Speed: O(N<sup>2</sup>)</p>
    """
    md, issues = converter.convert(raw_html)
    assert not issues
    assert "<video" in md
    assert "<audio" in md
    assert "<details>" in md
    assert "<summary>" in md
    assert "<sub>2</sub>" in md
    assert "<sup>2</sup>" in md


def test_converts_code_blocks_with_language_detection(converter):
    raw_html = """
    <pre class="brush: python"><code>def add(a, b):
    return a + b
    </code></pre>
    """
    md, issues = converter.convert(raw_html)
    assert not issues
    assert "```python" in md
    assert "def add(a, b):" in md
    assert "return a + b" in md
    assert "```" in md


def test_cleans_empty_blogger_divs_and_breaks(converter):
    raw_html = """
    <p>Paragraph 1</p>
    <div><br /></div>
    <div><br></div>
    <p>Paragraph 2</p>
    """
    md, issues = converter.convert(raw_html)
    assert not issues
    assert "<div>" not in md
    assert "<br" not in md
    assert "Paragraph 1\n\nParagraph 2" in md
