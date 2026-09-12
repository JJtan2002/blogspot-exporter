"""YAML frontmatter generator for ingested blog posts."""

from typing import Any, Dict, List, Optional
import yaml
from blogspot_ingestion.models import BlogPost


def build_frontmatter_data(
    post: BlogPost,
    classification: str = "personal_analysis",
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Construct the dictionary of metadata to be encoded into YAML frontmatter."""
    data: Dict[str, Any] = {
        "title": post.title,
        "date": post.published,
        "url": post.url or "",
        "labels": list(post.labels) if post.labels else [],
        "classification": classification,
        "type": classification,
        "id": post.id,
    }

    if post.updated:
        data["updated"] = post.updated

    if post.author_name:
        data["author"] = post.author_name

    if extra_metadata:
        data.update(extra_metadata)

    return data


def dump_yaml_frontmatter(data: Dict[str, Any]) -> str:
    """Dump dictionary as clean, standard YAML frontmatter bounded by ---."""
    # Use PyYAML safe_dump with specific formatting
    yaml_str = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()

    return f"---\n{yaml_str}\n---\n"


def create_post_markdown_content(
    post: BlogPost,
    markdown_body: str,
    classification: str = "personal_analysis",
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Combine YAML frontmatter and markdown body into a single ingestible document."""
    frontmatter_dict = build_frontmatter_data(
        post=post,
        classification=classification,
        extra_metadata=extra_metadata,
    )
    frontmatter_str = dump_yaml_frontmatter(frontmatter_dict)

    body_clean = markdown_body.strip()
    if body_clean:
        return f"{frontmatter_str}\n{body_clean}\n"
    return f"{frontmatter_str}\n"
