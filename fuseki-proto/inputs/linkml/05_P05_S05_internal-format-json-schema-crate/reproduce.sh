#!/bin/sh
# Reproduce 05_P05_S05_internal-format.schema.json from its LinkML source.
#
# Run from THIS directory (the crate root):
#
#     sh reproduce.sh
#
# Requirements: a Python environment matching environment/pip-freeze.txt
# (the run used Python 3.12.12 with linkml==1.11.1 / linkml-runtime==1.11.1,
# pinned for linkml-map==0.5.2 — see findings F8 in ../trafos/README.md).
# The schema's `imports: linkml:types` statement resolves, for these
# versions, to the bundled module archived as environment/linkml-types.yaml.
#
# Verification 2026-11-19: running this script over the archived source
# reproduced the archived 05_P05_S05_internal-format.schema.json
# byte-identically.
#
# Command as executed for the original run (repository root):
#   .venv/bin/gen-json-schema \
#     projecting_spaces/EDO/Artefacts/07_Fragments/scripts/linkml/05_P05_S05_internal-format-schema.yaml \
#     > projecting_spaces/EDO/Artefacts/07_Fragments/scripts/linkml/05_P05_S05_internal-format.schema.json

gen-json-schema 05_P05_S05_internal-format-schema.yaml \
    > 05_P05_S05_internal-format.schema.json
