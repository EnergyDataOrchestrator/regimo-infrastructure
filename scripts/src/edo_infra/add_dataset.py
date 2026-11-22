"""Add a "collection of papers to be analysed" dataset to an RDMO project XML.

Pure XML manipulation (no instance access): the command appends one
``project/dataset`` set instance to the ``<values>`` section of an RDMO
project XML export (as produced by ``create-project-from-doi`` or the web UI
export) and keeps the file importable by RDMO:

* the set value (attribute ``project/dataset/id``, ``set_prefix`` empty,
  ``set_index`` = next free index, ``set_collection=True``) carries the
  dataset's display name — RDMO/maDMP show the set row's text as the dataset
  name, and the maDMP exporter falls back to it for ``dataset_id``;
* ``description``, ``format`` and ``creation_methods`` member values
  (``set_prefix`` empty like the set value — RDMO's set_prefix is a chain of
  set indexes, not a path — and the same ``set_index``) describe the dataset
  as exactly as possible: a curated three-column list (Author, Publication
  Date, Title), one row per paper, compiled through literature search and
  analysed with the Semantico toolchain;
* ``--papers <csv>`` folds a concrete paper list (columns ``Author,
  Publication Date, Title``, header case-insensitive, fully empty rows
  skipped) into the description, the format value and the creation-methods
  value.

All values are re-sorted by (attribute URI, set index, collection index) like
RDMO's own exporter does, so the diff stays reviewable. Idempotency: a second
run with the same dataset name aborts (the set value already exists).
"""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import click

from .paths import DEFAULT_XML_DIR

DC = "http://purl.org/dc/elements/1.1/"
DC_URI = f"{{{DC}}}uri"
DOMAIN_BASE = "https://rdmorganiser.github.io/terms/domain/"
DATASET = "project/dataset"

DEFAULT_XML = DEFAULT_XML_DIR / "doi-10.5445-ir-1000162908.project.xml"
DEFAULT_ID = "Collection of papers to be analysed"

BASE_DESCRIPTION = (
    "Collection of scholarly papers to be analysed with the Semantico "
    "toolchain (literature classification and analysis workflow). The dataset "
    "is a structured, curated list in which each row describes exactly one "
    "paper with three columns: "
    "Author — the author(s) of the paper as given in the publication; "
    "Publication Date — the date (year, or full date when known) the paper "
    "was published; "
    "Title — the full title of the paper. "
    "The list is maintained by the project team through literature search and "
    "constitutes the input corpus of the analysis."
)


def load_papers(csv_path: Path) -> list[dict]:
    """Read a paper list CSV with the columns Author, Publication Date, Title."""
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise click.ClickException(f"{csv_path}: CSV has no header row")
        normalized = {(name or "").strip().lower(): name
                      for name in reader.fieldnames}

        def column(*keys: str) -> str:
            for key in keys:
                if key in normalized:
                    return normalized[key]
            raise click.ClickException(
                f"{csv_path}: CSV must have the columns "
                f"Author, Publication Date, Title (got: {', '.join(reader.fieldnames)})")

        col_author = column("author", "authors")
        col_date = column("publication date", "publicationdate", "date", "year")
        col_title = column("title")

        papers = []
        for line_no, row in enumerate(reader, start=2):
            author = (row.get(col_author) or "").strip()
            date = (row.get(col_date) or "").strip()
            title = (row.get(col_title) or "").strip()
            if not (author or date or title):
                continue  # fully empty row
            if not title:
                raise click.ClickException(
                    f"{csv_path}:{line_no}: row without Title: {author!r}, {date!r}")
            papers.append({"author": author, "date": date, "title": title})
    if not papers:
        raise click.ClickException(f"{csv_path}: no paper rows found")
    return papers


def papers_table(papers: list[dict]) -> str:
    lines = ["", "", f"Papers currently in the collection ({len(papers)}):",
             "Author | Publication Date | Title"]
    for i, paper in enumerate(papers, start=1):
        lines.append(f"{i}. {paper['author']} | {paper['date']} | {paper['title']}")
    return "\n".join(lines)


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def make_value(attr_path: str, *, set_prefix: str, set_index: int,
               set_collection: bool, collection_index: int, text: str) -> ET.Element:
    value = ET.Element("value")
    attribute = ET.SubElement(value, "attribute")
    attribute.set(DC_URI, DOMAIN_BASE + attr_path)
    ET.SubElement(value, "set_prefix").text = set_prefix or None
    ET.SubElement(value, "set_index").text = str(set_index)
    ET.SubElement(value, "set_collection").text = "True" if set_collection else "False"
    ET.SubElement(value, "collection_index").text = str(collection_index)
    ET.SubElement(value, "text").text = text or None
    ET.SubElement(value, "option")
    ET.SubElement(value, "file")
    ET.SubElement(value, "value_type").text = "text"
    ET.SubElement(value, "unit")
    ET.SubElement(value, "external_id")
    ET.SubElement(value, "created").text = timestamp()
    ET.SubElement(value, "updated").text = timestamp()
    return value


def sort_key(value: ET.Element) -> tuple:
    attribute = value.find("attribute")
    uri = attribute.get(DC_URI, "") if attribute is not None else ""

    def as_int(tag: str) -> int:
        element = value.find(tag)
        try:
            return int(element.text) if element is not None and element.text else 0
        except ValueError:
            return 0

    return (uri, as_int("set_index"), as_int("collection_index"))


def dataset_set_values(values: ET.Element) -> list[ET.Element]:
    """The ``project/dataset/id`` set rows (set_prefix empty)."""
    result = []
    for value in values.findall("value"):
        attribute = value.find("attribute")
        if attribute is None or attribute.get(DC_URI) != DOMAIN_BASE + f"{DATASET}/id":
            continue
        prefix = value.findtext("set_prefix") or ""
        if not prefix:
            result.append(value)
    return result


@click.command("add-dataset")
@click.option("--xml", "xml_path",
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=DEFAULT_XML, show_default=True,
              help="RDMO project XML fixture to extend.")
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path),
              default=None,
              help="Write the result here (default: modify --xml in place).")
@click.option("--id", "dataset_id", default=DEFAULT_ID, show_default=True,
              help="Name of the new dataset (set value text).")
@click.option("--papers",
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=None,
              help="CSV with the columns Author, Publication Date, Title — "
                   "one row per paper in the collection.")
@click.option("--dry-run", is_flag=True,
              help="Show the planned values; do not write anything.")
def add_dataset(xml_path: Path, out: Path | None, dataset_id: str,
                papers: Path | None, dry_run: bool):
    """Add a dataset (papers collection) to an RDMO project XML fixture."""
    papers = load_papers(papers) if papers else []
    description = BASE_DESCRIPTION + (papers_table(papers) if papers else "")
    format_text = (f"CSV ({len(papers)} rows; three columns: Author, "
                   "Publication Date, Title; one row per paper)" if papers else
                   "CSV (three columns: Author, Publication Date, Title; "
                   "one row per paper)")
    creation_methods = (
        "Compiled by the project team through literature search: papers "
        "relevant to the Semantico classification toolchain were collected "
        "manually, recording author(s), publication date and title for each."
        + (f" Currently {len(papers)} papers." if papers else ""))

    tree = ET.parse(xml_path)
    root = tree.getroot()
    values = root.find("values")
    if values is None:
        raise click.ClickException(f"{xml_path}: no <values> section")

    # -- idempotency + next set index ----------------------------------------
    existing = dataset_set_values(values)
    for value in existing:
        if (value.findtext("text") or "") == dataset_id:
            raise click.ClickException(
                f"{xml_path}: a dataset named {dataset_id!r} already exists "
                f"(set_index {value.findtext('set_index')}) — nothing to do")
    next_index = max((int(v.findtext("set_index") or 0) for v in existing),
                     default=-1) + 1

    new_values = [
        make_value(f"{DATASET}/id", set_prefix="", set_index=next_index,
                   set_collection=True, collection_index=0, text=dataset_id),
        make_value(f"{DATASET}/description", set_prefix="",
                   set_index=next_index, set_collection=True,
                   collection_index=0, text=description),
        make_value(f"{DATASET}/format", set_prefix="",
                   set_index=next_index, set_collection=True,
                   collection_index=0, text=format_text),
        make_value(f"{DATASET}/creation_methods", set_prefix="",
                   set_index=next_index, set_collection=True,
                   collection_index=0, text=creation_methods),
    ]

    click.echo(f"XML          : {xml_path}")
    click.echo(f"new dataset  : {dataset_id!r} (set_index {next_index}, "
               f"{len(papers)} paper(s))")
    for value in new_values:
        attribute = value.find("attribute").get(DC_URI)
        click.echo(f"  + {attribute} -> {(value.findtext('text') or '')[:80]!r}")

    if dry_run:
        click.echo("(dry-run) nothing written")
        return

    for value in new_values:
        values.append(value)
    values[:] = sorted(values, key=sort_key)

    ET.register_namespace("dc", DC)
    ET.indent(tree, space="\t")
    target = out or xml_path
    tree.write(target, encoding="utf-8", xml_declaration=True)
    click.echo(f"OK: wrote {target} ({target.stat().st_size} bytes, "
               f"dataset set_index {next_index})")
