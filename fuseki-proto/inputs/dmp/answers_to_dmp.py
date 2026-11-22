#!/usr/bin/env python3
"""EDO step 01 + 02 runner: raw RDMO answers -> Measurement_02.json -> maDMP.

Feasibility study (EDO) - step 02 "DMP Erstellung".

Pipeline
--------
1) Step 01: transform the raw RDMO export (`01_A01_answers_rdmo.json`, a list
   of question/answer entries) into the semantic answers object written to
   `Measurement_02.json` (``{"row": [{"key", "value"}, ...]}``). The mapping
   and extraction rules are NOT hard-coded here -- they live as annotations on
   the slots of the LinkML schema `01_P01_S01_rdmo-answers-schema.yaml`. This
   script is a generic driver that reads that schema and applies it.

2) Step 02: map the semantic answers to a maDMP. The LinkML Map specification
   `02_P02_S02_madmp-mapping.transform.yaml` maps the `RdmoAnswers` object to
   the target schema `madmp-lightmodel.yaml` via `linkml_map.session.Session`.

Both steps can run non-interactively (pure data transformation) or
interactively with `--ui`, which lets the user confirm/override each extracted
value before anything is written.

Usage
-----
    python answers_to_dmp.py                                  # both steps
    python answers_to_dmp.py --input foo.json
    python answers_to_dmp.py --ui                             # confirm each value
    python answers_to_dmp.py --step 1 --output Measurement_02.json
    python answers_to_dmp.py --step 2 --input Measurement_02.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from linkml_runtime.utils.schemaview import SchemaView
from linkml_map.session import Session

# Directory where this script and its sibling resources live.
BASE_DIR = Path(__file__).resolve().parent

# LinkML files that carry the transformation intelligence.
SOURCE_SCHEMA_PATH = BASE_DIR / "01_P01_S01_rdmo-answers-schema.yaml"
TRANSFORM_SPEC_PATH = BASE_DIR / "02_P02_S02_madmp-mapping.transform.yaml"
TARGET_SCHEMA_PATH = BASE_DIR / "madmp-lightmodel.yaml"

#: Semantic class (in the source schema) whose slots drive step-01 extraction.
MEASUREMENT_CLASS = "RdmoAnswers"


# --------------------------------------------------------------------------
# Step 01: generic, schema-driven RDMO export -> semantic answers
# --------------------------------------------------------------------------
def _extract_direct(answer: dict, _default: str | None) -> str | None:
    return answer.get("values")


def _extract_from_set(answer: dict, _default: str | None) -> str | None:
    # `set` looks like: Data Set "Weatherstation Q3-2026"
    set_value = answer.get("set", "")
    first = set_value.find('"')
    last = set_value.rfind('"')
    if first != -1 and last > first:
        return set_value[first + 1 : last]
    return set_value.strip() or None


def _extract_split_first(answer: dict, _default: str | None) -> str | None:
    values = answer.get("values", "")
    first = values.split(";")[0].strip()
    return first or None


def _extract_lower(answer: dict, _default: str | None) -> str | None:
    return answer.get("values", "").lower()


def _extract_mime(answer: dict, _default: str | None) -> str | None:
    # Map common RDMO file-format labels to MIME types.
    label = (answer.get("values") or "").strip()
    table = {
        "csv": "text/csv",
        "json": "application/json",
        "xml": "application/xml",
        "tiff": "image/tiff",
        "nc": "application/x-netcdf",
        "netcdf": "application/x-netcdf",
    }
    if not label:
        return None
    return table.get(label.lower(), label)


def _extract_default(_answer: dict, default: str | None) -> str | None:
    return default


EXTRACTORS = {
    "direct": _extract_direct,
    "from-set": _extract_from_set,
    "split-first": _extract_split_first,
    "lower": _extract_lower,
    "mime": _extract_mime,
    "default": _extract_default,
}


def _annotations(slot) -> dict:
    """Return slot annotations as a plain {name: value} dict.

    `induced_slot(...).annotations` comes back as a ``jsonasobj2.JsonObj``
    (tag attributes holding ``Annotation`` values), while ``all_slots()``
    returns a plain dict. Normalise both into ``{tag: value}``.
    """
    anns = slot.annotations
    if not anns:
        return {}
    if isinstance(anns, dict):
        return {name: ann.value for name, ann in anns.items()}
    result: dict = {}
    for name in vars(anns):
        if name.startswith("_"):
            continue
        ann = getattr(anns, name)
        result[name] = getattr(ann, "value", ann)
    return result


def read_mapping(source_schema: SchemaView) -> list[dict]:
    """Read the semantic mapping declared in the LinkML source schema.

    Returns one entry per slot of `MEASUREMENT_CLASS`, carrying `slot`,
    `question` (the RDMO question), `extract` (extractor name) and `default`.
    """
    mapping = []
    for slot_name in source_schema.class_slots(MEASUREMENT_CLASS):
        slot = source_schema.induced_slot(slot_name, MEASUREMENT_CLASS)
        anns = _annotations(slot)
        question = anns.get("rdmo_question")
        extract = anns.get("rdmo_extract", "direct")
        default = anns.get("rdmo_default")
        if question is None and extract != "default":
            raise ValueError(
                f"slot '{slot_name}' of '{MEASUREMENT_CLASS}' has no "
                "'rdmo_question' annotation (and is not 'default')"
            )
        mapping.append(
            {"slot": slot_name, "question": question, "extract": extract, "default": default}
        )
    return mapping


def build_measurement(
    export: dict,
    mapping: list[dict],
    *,
    interactive: bool = False,
) -> dict:
    """Apply the schema-declared mapping to the raw RDMO export.

    Returns the wide `RdmoAnswers` object (a dict keyed by slot name).
    When `interactive` is true, each extracted value is shown on stdout and can
    be accepted (Enter) or overridden before the object is returned.

    `export` may be either a flat ``list`` of ``{question, set, values}`` (the
    shape of ``01_A01_answers_rdmo.json``) or a dict shaped
    ``{"answer": [ ... ]}``; both are normalised to the same internal list.
    """
    if isinstance(export, dict):
        answers = export.get("answer", [])
    else:
        answers = export

    by_question: dict[str, dict] = {}
    for answer in answers:
        question = answer.get("question")
        if question:
            by_question[question] = answer  # later answers win on duplicates

    wide: dict = {}
    for entry in mapping:
        name = entry["slot"]
        extract = EXTRACTORS.get(entry["extract"])
        if extract is None:
            raise ValueError(f"unknown rdmo_extract '{entry['extract']}' for slot '{name}'")

        answer = by_question.get(entry["question"]) if entry["question"] else None
        value = extract(answer, entry["default"]) if answer else entry["default"]

        if interactive:
            question_label = entry["question"] or "(no question; default)"
            raw = answer["values"] if answer else "(none)"
            print(f"[{name}] {question_label}")
            print(f"    raw value : {raw!r}")
            print(f"    extracted : {value!r}")
            choice = input("    accept [Enter] / edit [new value] / skip [s]: ").strip()
            if choice.lower() == "s":
                continue
            if choice:
                value = choice

        if value is not None:
            wide[name] = value
    return wide


def to_row_form(wide: dict) -> dict:
    """Serialise the wide semantic answers into ``{"row": [{key, value}]}``."""
    return {"row": [{"key": key, "value": value} for key, value in wide.items()]}


# --------------------------------------------------------------------------
# Step 02: semantic answers -> maDMP (LinkML Map via linkml_map.session)
# --------------------------------------------------------------------------
def run_transform(
    input_data: dict,
    source_schema: SchemaView,
    transform_spec: str | Path,
    target_schema: str | Path,
    verbose: bool = True,
) -> str:
    """Map the wide semantic answers to a maDMP; return the JSON string."""
    session = Session()
    session.set_source_schema(source_schema)
    session.set_object_transformer(transform_spec)
    # ObjectDerivation resolution needs the target schema to know whether the
    # target slot is single- or multi-valued. LinkML's Session only wires up
    # the source schema, so expose the target schema view explicitly.
    transformer = session.object_transformer
    assert transformer is not None  # set by set_object_transformer above
    transformer.target_schemaview = SchemaView(str(target_schema))

    mapped = session.transform(input_data, source_type=MEASUREMENT_CLASS)
    if verbose:
        print("== Transformed object ==")
        print(json.dumps(mapped, indent=2, default=str), file=sys.stderr)

    # ``mapped`` is already a plain dict (the transformer returns dicts);
    # dump with the stdlib serializer to avoid ``@type`` noise.
    return json.dumps(mapped, indent=2, default=str)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Transform raw RDMO answers into Measurement_02.json and a maDMP.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=BASE_DIR / "01_A01_answers_rdmo.json",
        help="Raw RDMO answers export (JSON) for step 01; or a Measurement JSON for --step 2.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BASE_DIR / "Measurement_02.json",
        help="Where to write the semantic answers (step 01).",
    )
    parser.add_argument(
        "--dmp-output",
        type=Path,
        default=BASE_DIR / "Measurement_02.dmp.json",
        help="Where to write the maDMP (step 02).",
    )
    parser.add_argument(
        "--step",
        type=int,
        choices=(1, 2),
        default=None,
        help="Run only step 1 or step 2; omit to run both.",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Interactive mode: confirm/override each extracted value.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the human-readable dump on stderr.",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        parser.error(f"input file not found: {args.input}")
    for label, path in (
        ("source schema", SOURCE_SCHEMA_PATH),
        ("transform spec", TRANSFORM_SPEC_PATH),
        ("target schema", TARGET_SCHEMA_PATH),
    ):
        if not path.exists():
            parser.error(f"{label} not found: {path}")

    source_sv = SchemaView(str(SOURCE_SCHEMA_PATH))

    # Reused as the step-02 source when both steps run.
    wide: dict = {}

    # Step 1: raw RDMO export -> semantic answers (unless only step 2).
    if args.step in (None, 1):
        export = json.loads(args.input.read_text(encoding="utf-8"))
        mapping = read_mapping(source_sv)
        wide = build_measurement(export, mapping, interactive=args.ui)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(to_row_form(wide), indent=2), encoding="utf-8")
        if not args.quiet:
            print(f"[step 01] wrote {args.output}")

    # Step 2: semantic answers -> maDMP.
    if args.step in (None, 2):
        # Source for step 2 is the semantic answers object. Reuse the step-01
        # result when both steps run; otherwise reify a Measurement JSON input.
        if args.step is None:
            step2_wide = wide
        else:
            measurement = json.loads(args.input.read_text(encoding="utf-8"))
            step2_wide = {r["key"]: r["value"] for r in measurement.get("row", [])}

        try:
            output_json = run_transform(
                step2_wide,
                source_sv,
                str(TRANSFORM_SPEC_PATH),
                TARGET_SCHEMA_PATH,
                verbose=not args.quiet,
            )
        except Exception as exc:  # pragma: no cover - surfaced to the user
            print(f"[step 02] Transformation failed: {exc}", file=sys.stderr)
            return 1

        args.dmp_output.parent.mkdir(parents=True, exist_ok=True)
        args.dmp_output.write_text(output_json, encoding="utf-8")
        if not args.quiet:
            print(f"[step 02] wrote {args.dmp_output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
