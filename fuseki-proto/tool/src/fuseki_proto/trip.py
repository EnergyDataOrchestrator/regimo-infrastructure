"""trip.py — end-to-end round-trip realisation of card CF2-003.

Implements the three acceptance scenarios of card CF2-003 ("Transformationen
von DMP und SMS ins interne Format") against a concrete instance:

  1. **Transformation rules documented** — `transform` applies the catalogue in
     `scripts/trafos/patterns.md` (rules P1–P42, S1–S16) to the maDMP export
     `scripts/dmp/measurement_02/Measurement_02-13.json` and the SMS device
     `scripts/sms/device-67.json` (+ device-property files) and records every
     applied rule, translation decision and documented loss in the report.
  2. **The transformed project is stored** — `store` wipes and (re)loads the
     internal-format graph into the `/projects` TDB2 dataset, confirms
     retrievability via SPARQL and (when `pyshacl` is on PATH) validates the
     graph against `shapes/project-claim-shapes.ttl`.
  3. **Round-trip preserves the data** — `verify` dumps `/projects` back out,
     re-uploads the dump into the named replay graph `<urn:edo:trip:replay>`
     and runs field-level checks that compare the DUMP against the ORIGINAL
     DMP and SMS sources (positive checks per mapped field, negative checks
     per documented loss, plus a default-vs-replay triple-count comparison).

`run` executes all three stages in one go. Artifacts are written to
`data/trip/<timestamp>/` next to the prototype's `data/` directory:

  * `project-graph.ttl`    — the transformed internal-format instance graph
  * `roundtrip-dump.ttl`   — the Turtle dump served back by Fuseki
  * `trip-report.json`     — applied rules, notes, checks and verdicts

Run it either standalone (``python -m fuseki_proto.trip run``) or through the
maintenance CLI (``fuseki-proto trip run``).
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

import click

from . import docker as D

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
TOOL_DIR = D.TOOL_DIR                      # .../fuseki-proto/tool
PROTO_DIR = TOOL_DIR.parent                # .../fuseki-proto
SCRIPTS_DIR = PROTO_DIR.parent             # .../scripts
DMP_DEFAULT = SCRIPTS_DIR / "dmp" / "measurement_02" / "Measurement_02-13.json"
SMS_DIR = SCRIPTS_DIR / "sms"
DEVICE_DEFAULT = SMS_DIR / "device-67.json"
SHAPES_FILE = PROTO_DIR / "shapes" / "project-claim-shapes.ttl"
TRIP_DIR = PROTO_DIR / "data" / "trip"

# ---------------------------------------------------------------------------
# namespaces / constants
# ---------------------------------------------------------------------------
EDO = "https://w3id.org/edo/terms/"
DCTERMS = "http://purl.org/dc/terms/"
DCAT = "http://www.w3.org/ns/dcat#"
FOAF = "http://xmlns.com/foaf/0.1/"
PROV = "http://www.w3.org/ns/prov#"
TIME = "http://www.w3.org/2006/time#"
SOSA = "http://www.w3.org/ns/sosa/"
SMSCV = "https://sms-cv.helmholtz.cloud/sms/cv/api/v1/"
XSD = "http://www.w3.org/2001/XMLSchema#"
MEDIATYPE = "http://purl.org/NET/mediatypes/"
SMS_DEVICE_BASE = "https://sms.atmohub.kit.edu/devices/"
REPLAY_GRAPH = "urn:edo:trip:replay"

TTL_PREFIXES = f"""@prefix edo:    <{EDO}> .
@prefix dcterms: <{DCTERMS}> .
@prefix dcat:   <{DCAT}> .
@prefix foaf:   <{FOAF}> .
@prefix prov:   <{PROV}> .
@prefix time:   <{TIME}> .
@prefix sosa:   <{SOSA}> .
@prefix smscv:  <{SMSCV}> .
@prefix xsd:    <{XSD}> ."""

SPARQL_PREFIXES = (
    f"PREFIX edo: <{EDO}>\n"
    f"PREFIX dcterms: <{DCTERMS}>\n"
    f"PREFIX dcat: <{DCAT}>\n"
    f"PREFIX foaf: <{FOAF}>\n"
    f"PREFIX prov: <{PROV}>\n"
    f"PREFIX time: <{TIME}>\n"
    f"PREFIX sosa: <{SOSA}>\n"
    f"PREFIX smscv: <{SMSCV}>\n"
    f"PREFIX xsd: <{XSD}>\n"
)

# ---------------------------------------------------------------------------
# mapping tables (scripts/trafos/patterns.md)
# ---------------------------------------------------------------------------
# P8: role_template free text -> RDA maDMP contributor-type CV. First matching
# regex wins; anything unmatched falls back to "Other" (documented default).
ROLE_TRANSLATION = [
    (re.compile(r"responsible for preservation", re.I), "Data Curator"),
    (re.compile(r"responsible for metadata", re.I), "Data Curator"),
]
ROLE_FALLBACK = "Other"

# P34: RDMO free-text format labels -> IANA media types (spec §3.3 decision
# 2026-11-19). Emitted as IANA media-type IRIs, following
# fuseki-proto/data/sample-project.ttl.
FORMAT_TRANSLATION = [
    (re.compile(r"\bcsv\b", re.I), "text/csv"),
    (re.compile(r"\bjson\b", re.I), "application/json"),
    (re.compile(r"\bxls(x)?\b|\bexcel\b", re.I), "application/vnd.ms-excel"),
    (re.compile(r"\bnetcdf\b", re.I), "application/netcdf"),
    (re.compile(r"\bpdf\b", re.I), "application/pdf"),
    (re.compile(r"\bxml\b", re.I), "application/xml"),
]

# S10–S12: datasheet overrides (authority per CF1-005 / spec open item 7),
# keyed by the SMS-CV measured-quantity URI. SMS itself reports -80…+60 and
# null accuracy/resolution; the datasheet wins for the air-temperature probe.
DATASHEET_OVERRIDES = {
    f"{SMSCV}measuredquantities/4/": {
        "measuring_range_min": -40.0,
        "measuring_range_max": 80.0,
        "accuracy": "±0.3 K @ 25 °C; ±1.0 K over -40…+80 °C",
        "resolution": 0.1,
    },
}

PIDINST_RE = re.compile(r"PIDINST:\s*(\S+)", re.I)


# ---------------------------------------------------------------------------
# Turtle helpers
# ---------------------------------------------------------------------------
def ttl_escape(text: str) -> str:
    return (str(text).replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))


def sparql_str(text: str) -> str:
    return '"' + (str(text).replace("\\", "\\\\").replace('"', '\\"')
                  .replace("\n", "\\n").replace("\r", "\\r")) + '"'


def iri(value: str) -> str:
    return f"<{value}>"


def date_lit(value: str) -> str:
    return f'"{value}"^^xsd:date'


def dec_lit(value) -> str:
    return f'"{value}"^^xsd:decimal'


class TurtleGraph:
    """Tiny deterministic Turtle serializer (grouped per subject)."""

    def __init__(self):
        self._order: list[str] = []
        self._stmts: dict[str, list[tuple[str, str]]] = {}

    def add(self, subject: str, predicate: str, obj: str) -> None:
        if subject not in self._stmts:
            self._stmts[subject] = []
            self._order.append(subject)
        self._stmts[subject].append((predicate, obj))

    def turtle(self) -> str:
        out = [TTL_PREFIXES, ""]
        for subject in self._order:
            pairs = self._stmts[subject]
            blocks: list[str] = []
            i = 0
            while i < len(pairs):
                predicate = pairs[i][0]
                objects: list[str] = []
                while i < len(pairs) and pairs[i][0] == predicate:
                    objects.append(pairs[i][1])
                    i += 1
                joined = " ,\n        ".join(objects)
                blocks.append(f"    {predicate} {joined}")
            out.append(f"{subject}\n    " + " ;\n    ".join(blocks) + " .\n")
        return "\n".join(out)


class Builder:
    """Builds the graph, the verification checks and the audit trail."""

    def __init__(self):
        self.g = TurtleGraph()
        self.bnode_n = 0
        self.rules: list[dict] = []
        self.notes: list[str] = []
        self.checks: list[dict] = []

    def bnode(self) -> str:
        self.bnode_n += 1
        return f"_:b{self.bnode_n}"

    def rule(self, rule: str, detail: str) -> None:
        self.rules.append({"rule": rule, "detail": detail})

    def note(self, text: str) -> None:
        self.notes.append(text)

    def check(self, cid: str, rule: str, source: str, description: str,
              pattern: str, expect: bool = True) -> None:
        """Positive check: pattern must occur; negative: pattern must not."""
        self.checks.append({
            "id": cid, "rule": rule, "source": source, "description": description,
            "kind": "absent" if not expect else "present",
            "pattern": pattern,
        })

    def count_check(self, cid: str, rule: str, source: str, description: str,
                    pattern: str, expect: int) -> None:
        self.checks.append({
            "id": cid, "rule": rule, "source": source, "description": description,
            "kind": "count", "pattern": pattern, "expect": expect,
        })


# ---------------------------------------------------------------------------
# transformation (scenario 1 -> scenario 2)
# ---------------------------------------------------------------------------
def transform(dmp: dict, device: dict | None, properties: list[dict]):
    """Apply the patterns.md catalogue to the sources.

    Returns ``(turtle, checks, report_meta)`` where ``report_meta`` carries the
    applied rules, decisions and documented losses.
    """
    b = Builder()
    g = b.g
    d = dmp["dmp"]

    dmp_id = d["dmp_id"]["identifier"]
    project = iri(dmp_id)
    proj = d["project"][0]

    # --- Project (P1–P9) ----------------------------------------------------
    # P1: project/title -> Project dcterms:title. NB: spec §4's example
    # coincidentally carries the *DMP* title ("maDMP for Measurement_02");
    # the catalogue rule P1 maps project/title, which is followed here.
    title = proj["title"]
    g.add(project, "a", "edo:Project")
    g.add(project, "dcterms:title", f'"{ttl_escape(title)}"')
    b.rule("P1", f"project/title {title!r} -> dcterms:title (1:1)")

    if proj.get("description"):
        g.add(project, "dcterms:description", f'"{ttl_escape(proj["description"])}"')
        b.rule("P2", "project/description -> dcterms:description (1:1)")

    language = d.get("language") or "eng"
    g.add(project, "dcterms:language", f'"{language}"')
    b.rule("P3", f"language absent in export -> default {language!r} (omit → default)")

    if proj.get("start") or proj.get("end"):
        interval = b.bnode()
        g.add(project, "time:hasInterval", interval)
        if proj.get("start"):
            g.add(interval, "time:hasBeginning", date_lit(proj["start"]))
        if proj.get("end"):
            g.add(interval, "time:hasEnd", date_lit(proj["end"]))
        b.rule("P4", f"project/start,end {proj.get('start')}…{proj.get('end')} "
                     "-> time:hasInterval node (cast -> xsd:date)")

    dmp_id_node = b.bnode()
    g.add(project, "edo:dmpId", dmp_id_node)
    g.add(dmp_id_node, "dcterms:identifier", f'"{ttl_escape(dmp_id)}"')
    g.add(dmp_id_node, "dcterms:type", f'"{d["dmp_id"]["type"]}"')
    b.rule("P5/P16/P17", f"dmp_id {dmp_id!r} (type {d['dmp_id']['type']!r}) "
                         "-> edo:dmpId Identifier node")

    if d.get("contact"):
        contact = b.bnode()
        g.add(project, "edo:hasContact", contact)
        g.add(contact, "a", "foaf:Person")
        g.add(contact, "foaf:name", f'"{ttl_escape(d["contact"]["name"])}"')
        if d["contact"].get("mbox"):
            g.add(contact, "foaf:mbox", iri(f"mailto:{d['contact']['mbox']}"))
        b.rule("P6/P10/P11", "contact -> edo:hasContact Person node")
    else:
        b.rule("P6", "no contact in export -> omitted (documented mapping)")
        b.note("EDGE CASE: the export carries no `contact`, but "
               "edo:ProjectShape requires edo:hasContact (sh:minCount 1). "
               "Faithful P6 behaviour (omit) therefore trips the SHACL claim "
               "— conflict between patterns.md P6 and project-claim-shapes.ttl, "
               "needs a decision (relax shape vs. guarantee contact in export).")

    contributions = []
    for contrib in d.get("contributor", []):
        c = b.bnode()
        agent = b.bnode()
        g.add(c, "a", "edo:Contribution")
        g.add(c, "prov:agent", agent)
        g.add(agent, "a", "foaf:Person")
        name = contrib["name"].strip()
        g.add(agent, "foaf:name", f'"{ttl_escape(name)}"')
        b.rule("P10", f"contributor name {name!r} -> foaf:name (1:1)")
        if contrib.get("mbox"):
            mbox = f"mailto:{contrib['mbox'].strip()}"
            # foaf:PersonShape types foaf:mbox as xsd:anyURI (spec §3.2) — an
            # IRI has no datatype and would violate the shape, so emit a typed
            # literal instead.
            g.add(agent, "foaf:mbox", f'"{ttl_escape(mbox)}"^^xsd:anyURI')
            b.rule("P11", "contributor mbox -> foaf:mbox (cast -> mailto: URI, xsd:anyURI literal)")
        role_raw = " / ".join(contrib.get("role", []))
        role = ROLE_FALLBACK
        for pattern, cv in ROLE_TRANSLATION:
            if pattern.search(role_raw):
                role = cv
                break
        g.add(c, "dcterms:type", f'"{role}"')
        b.rule("P7/P8", f"contributor {name!r} role {role_raw!r} -> "
                        f"Contribution dcterms:type {role!r} (translate; "
                        f"unmapped templates default to {ROLE_FALLBACK!r})")
        contributions.append(c)
    for c in contributions:
        g.add(project, "edo:hasContribution", c)
    if not contributions:
        b.rule("P7", "no contributors -> omitted")

    if d.get("cost"):
        b.rule("P9", f"{len(d['cost'])} cost(s) -> edo:hasCost Cost nodes")
    else:
        b.rule("P9", "no costs in export -> omitted")

    # --- Datasets (P18–P30) --------------------------------------------------
    for ds in d.get("dataset", []):
        ds_id = (ds.get("dataset_id") or {}).get("identifier") or f"Dataset #{d['dataset'].index(ds) + 1}"
        ds_type = (ds.get("dataset_id") or {}).get("type", "other")
        dataset = iri(f"{dmp_id}/dataset:{urllib.parse.quote(str(ds_id), safe='')}")
        g.add(project, "dcat:dataset", dataset)
        g.add(dataset, "a", "dcat:Dataset")

        id_node = b.bnode()
        g.add(dataset, "edo:identifier", id_node)
        g.add(id_node, "dcterms:identifier", f'"{ttl_escape(str(ds_id))}"')
        g.add(id_node, "dcterms:type", f'"{ds_type}"')
        b.rule("P18", f"dataset_id {ds_id!r} (type {ds_type!r}) -> "
                      "edo:identifier Identifier node")

        g.add(dataset, "dcterms:title", f'"{ttl_escape(ds["title"])}"')
        b.rule("P19", f"dataset title {ds['title']!r} -> dcterms:title (1:1)")

        if ds.get("description"):
            g.add(dataset, "dcterms:description", f'"{ttl_escape(ds["description"])}"')
            b.rule("P20", "dataset description -> dcterms:description (1:1)")

        if ds.get("issued"):
            g.add(dataset, "dcterms:issued", date_lit(ds["issued"]))
            b.rule("P21", f"issued {ds['issued']!r} -> dcterms:issued (cast -> xsd:date)")

        if ds.get("type"):
            g.add(dataset, "dcterms:type", f'"{ds["type"]}"')
            b.rule("P22", f"dataset type {ds['type']!r} -> dcterms:type (1:1 CV)")
        else:
            b.rule("P22", "dataset `type` absent in export -> omitted (RDMO "
                          "template default not materialised in this export)")

        for kw in ds.get("keyword", []):
            g.add(dataset, "dcat:keyword", f'"{ttl_escape(kw)}"')
        b.rule("P23", f"keywords {ds.get('keyword', [])} -> dcat:keyword (array passthrough)")

        personal = {"yes": True, "no": False}.get(
            str(ds.get("personal_data", "")).lower(), False)
        sensitive = {"yes": True, "no": False}.get(
            str(ds.get("sensitive_data", "")).lower(), False)
        g.add(dataset, "edo:personalData", "true" if personal else "false")
        g.add(dataset, "edo:sensitiveData", "true" if sensitive else "false")
        b.rule("P24/P25", f"personal_data={ds.get('personal_data')!r}, "
                          f"sensitive_data={ds.get('sensitive_data')!r} -> "
                          f"edo:personalData {personal}, edo:sensitiveData {sensitive} "
                          "(maDMP yes/no CV -> xsd:boolean; unknown/absent -> false)")

        for item in ds.get("data_quality_assurance", []):
            g.add(dataset, "edo:qualityAssurance", f'"{ttl_escape(item)}"')
        b.rule("P26", f"data_quality_assurance items list -> edo:qualityAssurance "
                      f"array of {len(ds.get('data_quality_assurance', []))} (split)")

        if ds.get("preservation_statement"):
            g.add(dataset, "edo:preservationStatement",
                  f'"{ttl_escape(ds["preservation_statement"])}"')
            b.rule("P27", "preservation_statement -> edo:preservationStatement (join/1:1)")

        if ds.get("security_and_privacy"):
            b.rule("P28", "security_and_privacy present in source but has NO v0.2 "
                          "target class -> LOST (documented; spec gap)")
            b.note("LOST (P28): security_and_privacy "
                   f"{json.dumps(ds['security_and_privacy'], ensure_ascii=False)} "
                   "is dropped — no target property in internal-format v0.2.")

        # P30: dataset<->sensor link, today only via PIDINST: free text
        match = PIDINST_RE.search(ds.get("description") or "")
        if match:
            b.rule("P30", f"PIDINST {match.group(1)!r} extracted from description "
                          "-> prov:wasGeneratedBy (gap #18 free-text workaround)")
        else:
            b.rule("P30", "no PIDINST fragment in dataset description -> no "
                          "prov:wasGeneratedBy link (gap #18: machine-readable "
                          "dataset<->sensor link not representable today)")
            b.note("LOST (P30/gap #18): this dataset carries no PIDINST fragment, "
                   "so the SMS sensor is emitted as a standalone node and NOT "
                   "linked to the dataset.")

        # --- Distributions (P29, P31–P39) ------------------------------------
        for idx, dist in enumerate(ds.get("distribution", [])):
            dist_node = b.bnode()
            g.add(dataset, "dcat:distribution", dist_node)
            g.add(dist_node, "a", "dcat:Distribution")
            is_during = idx == 0

            dist_title = dist.get("title") or (
                "Storage during the project" if is_during
                else "Preservation after the project")
            g.add(dist_node, "dcterms:title", f'"{ttl_escape(dist_title)}"')
            b.rule("P31", f"distribution title {dist_title!r} -> dcterms:title "
                          "(fixed constant from the RDMO template)")

            if dist.get("access_url"):
                g.add(dist_node, "dcat:accessURL", iri(dist["access_url"]))
                b.rule("P32", f"access_url {dist['access_url']!r} -> dcat:accessURL (1:1 URI)")

            access = dist.get("data_access", "closed")
            g.add(dist_node, "edo:dataAccess", f'"{access}"')
            b.rule("P33", f"data_access {access!r} -> edo:dataAccess "
                          f"({'during: 1:1 CV' if is_during else 'after: derived, present in export'})")

            formats = []
            for fmt in dist.get("format", []):
                for pattern, media in FORMAT_TRANSLATION:
                    if pattern.search(fmt):
                        formats.append(media)
            for media in sorted(set(formats)):
                g.add(dist_node, "dcat:format", iri(f"{MEDIATYPE}{media}"))
            if formats:
                b.rule("P34", f"format {dist.get('format')} -> dcat:format "
                              f"{sorted(set(formats))} (free text -> IANA media types)")
            else:
                b.rule("P34", f"format {dist.get('format')} -> no IANA match -> omitted")

            if not is_during:
                pid_values = dist.get("pid_system") or []
                if isinstance(pid_values, str):
                    pid_values = [pid_values]
                for pid in pid_values:
                    g.add(dist_node, "edo:pidSystem", f'"{pid}"')
                if pid_values:
                    b.rule("P36", f"pid_system {pid_values} -> edo:pidSystem (1:1 CV)")
                host = dist.get("host") or {}
                if host.get("title"):
                    host_node = b.bnode()
                    g.add(dist_node, "edo:hostedBy", host_node)
                    g.add(host_node, "a", "edo:Host")
                    g.add(host_node, "dcterms:title", f'"{ttl_escape(host["title"])}"')
                    if host.get("url"):
                        g.add(host_node, "edo:url", iri(host["url"]))
                    b.rule("P37/P40", f"host {host['title']!r} -> edo:hostedBy Host node "
                                      "(url nullable, absent -> omitted)")
                for lic in dist.get("license", []) or []:
                    lic_node = b.bnode()
                    g.add(dist_node, "edo:license", lic_node)
                    g.add(lic_node, "a", "dcterms:LicenseDocument")
                    if lic.get("license_ref"):
                        g.add(lic_node, "dcterms:license", iri(lic["license_ref"]))
                        b.rule("P38/P41", f"license_ref {lic['license_ref']!r} -> "
                                          "License dcterms:license (option CV)")
                    if lic.get("start_date"):
                        g.add(lic_node, "time:hasBeginning", date_lit(lic["start_date"]))
                        b.rule("P39/P42", f"license start {lic['start_date']!r} -> "
                                          "License time:hasBeginning (cast -> xsd:date)")

    # --- SMS device -> Sensor (S1–S6) ----------------------------------------
    if device:
        attrs = device["data"]["attributes"]
        device_id = device["data"]["id"]
        sensor = iri(f"{SMS_DEVICE_BASE}{device_id}")

        g.add(sensor, "a", "sosa:Sensor")
        name = (attrs.get("short_name") or attrs.get("long_name")
                or attrs.get("device_type_name") or f"{SMS_DEVICE_BASE}{device_id}").strip()
        g.add(sensor, "dcterms:title", f'"{ttl_escape(name)}"')
        b.rule("S1", f"device short_name {name!r} -> Sensor dcterms:title (1:1)")

        if attrs.get("model"):
            g.add(sensor, "edo:model", f'"{ttl_escape(attrs["model"].strip())}"')
            b.rule("S2", f"model {attrs['model']!r} -> edo:model (1:1)")

        if attrs.get("manufacturer_name"):
            manufacturer = attrs["manufacturer_name"].strip()
            g.add(sensor, "edo:manufacturer", f'"{ttl_escape(manufacturer)}"')
            b.rule("S3", "manufacturer_name -> edo:manufacturer (1:1, whitespace normalised)")

        if attrs.get("device_type_uri"):
            g.add(sensor, "dcterms:type", iri(attrs["device_type_uri"]))
            b.rule("S4", "device_type_uri -> dcterms:type (SMS-CV URI passthrough; "
                         "device_type_name label dropped — documented loss)")

        if attrs.get("persistent_identifier"):
            pid_node = b.bnode()
            g.add(sensor, "edo:identifier", pid_node)
            g.add(pid_node, "dcterms:identifier",
                  f'"{ttl_escape(attrs["persistent_identifier"])}"')
            g.add(pid_node, "dcterms:type", '"handle"')
            b.rule("S5", f"persistent_identifier {attrs['persistent_identifier']!r} "
                         "-> edo:identifier Identifier node (type handle)")

        b.rule("S6", f"device IRI minted as {SMS_DEVICE_BASE}{device_id} "
                     "(SMS API path /devices/67 + EDO base URL)")

        # --- SMS device properties -> MeasuredProperty (S7–S16) ---------------
        for prop in properties:
            attrs_p = prop["data"]["attributes"]
            prop_id = prop["data"]["id"]
            prop_uri = attrs_p["property_uri"]
            prop_node = b.bnode()
            g.add(sensor, "sosa:observes", prop_node)
            g.add(prop_node, "a", "sosa:ObservableProperty")

            g.add(prop_node, "smscv:measuredQuantity", iri(prop_uri))
            b.rule("S7", f"property_uri {prop_uri} -> smscv:measuredQuantity (URI passthrough)")

            if attrs_p.get("property_name"):
                g.add(prop_node, "dcterms:title", f'"{ttl_escape(attrs_p["property_name"])}"')
                b.rule("S8", f"property_name {attrs_p['property_name']!r} -> dcterms:title (1:1)")

            if attrs_p.get("unit_uri"):
                g.add(prop_node, "edo:unit", iri(attrs_p["unit_uri"]))
                b.rule("S9", f"unit_uri -> edo:unit (SMS-CV URI passthrough; "
                             f"unit_name {attrs_p.get('unit_name')!r} dropped)")

            override = DATASHEET_OVERRIDES.get(prop_uri, {})
            range_min = override.get("measuring_range_min", attrs_p.get("measuring_range_min"))
            range_max = override.get("measuring_range_max", attrs_p.get("measuring_range_max"))
            accuracy = override.get("accuracy", attrs_p.get("accuracy"))
            resolution = override.get("resolution", attrs_p.get("resolution"))

            if range_min is not None:
                g.add(prop_node, "edo:measuringRangeMin", dec_lit(range_min))
            if range_max is not None:
                g.add(prop_node, "edo:measuringRangeMax", dec_lit(range_max))
            if override:
                b.rule("S10", f"measuring range SMS {attrs_p.get('measuring_range_min')}…"
                              f"{attrs_p.get('measuring_range_max')} OVERRIDDEN by datasheet "
                              f"{range_min}…{range_max} (authority per CF1-005; spec open item 7)")
            else:
                b.rule("S10", f"measuring range {range_min}…{range_max} (cast -> xsd:decimal)")

            if accuracy is not None:
                g.add(prop_node, "edo:accuracy", f'"{ttl_escape(accuracy)}"')
                b.rule("S11", f"accuracy SMS={attrs_p.get('accuracy')!r} -> datasheet "
                              f"{accuracy!r} (default-injection, authoritative override)")
            if resolution is not None:
                g.add(prop_node, "edo:resolution", dec_lit(resolution))
                b.rule("S12", f"resolution SMS={attrs_p.get('resolution')!r} -> datasheet "
                              f"{resolution} (default-injection, authoritative override)")

            if attrs_p.get("sampling_media_uri"):
                g.add(prop_node, "smscv:samplingMedia", iri(attrs_p["sampling_media_uri"]))
                b.rule("S13", f"sampling_media_uri -> smscv:samplingMedia (URI passthrough; "
                              f"name {attrs_p.get('sampling_media_name')!r} dropped)")
            if attrs_p.get("compartment_uri"):
                g.add(prop_node, "smscv:compartment", iri(attrs_p["compartment_uri"]))
                b.rule("S14", "compartment_uri -> smscv:compartment (URI passthrough)")
            if attrs_p.get("aggregation_type_uri"):
                g.add(prop_node, "edo:aggregationType", iri(attrs_p["aggregation_type_uri"]))
                b.rule("S15", f"aggregation_type_uri -> edo:aggregationType (URI passthrough; "
                              f"name {attrs_p.get('aggregation_type_name')!r} dropped)")
            b.rule("S16", f"device_property {prop_id} -> sosa:observes MeasuredProperty node")

    # -------------------------------------------------------------------------
    # verification checks (run later against the default graph AND the replay
    # graph produced by re-uploading the round-trip dump)
    # -------------------------------------------------------------------------
    _build_checks(b, dmp, device, properties)

    meta = {
        "project_iri": dmp_id,
        "dataset_iri": f"{dmp_id}/dataset:…",
        "sensor_iri": None,
        "rules": b.rules,
        "notes": b.notes,
    }
    if device:
        meta["sensor_iri"] = f"{SMS_DEVICE_BASE}{device['data']['id']}"
    return g.turtle(), b.checks, meta


def _build_checks(b: Builder, dmp: dict, device: dict | None,
                  properties: list[dict]) -> None:
    """Field-level checks comparing the (dumped) graph against the sources."""
    d = dmp["dmp"]
    proj_list = d.get("project") or []
    proj = proj_list[0] if proj_list else {}
    dmp_id = d["dmp_id"]["identifier"]

    P = "edo:Project"
    # F3: project/title is canonical; partial maDMPs without a dmp/project
    # array fall back to the maDMP-level title (matches the map fallback).
    p_title = proj.get("title") or d.get("title")

    def proj_pat(rest: str) -> str:
        return f"?p a {P} . {rest}"

    b.check("C01", "P1", "DMP project/title", f"Project dcterms:title {p_title!r}",
            proj_pat(f'?p dcterms:title {sparql_str(p_title)}'))
    if proj.get("description"):
        b.check("C02", "P2", "DMP project/description", "Project description carried",
                proj_pat(f'?p dcterms:description {sparql_str(proj["description"])}'))
    b.check("C03", "P3", "DMP language (absent -> default)", 'dcterms:language "eng"',
            proj_pat('?p dcterms:language "eng"'))
    if proj:
        b.check("C04", "P4", "DMP project start/end", f"interval {proj.get('start')}…{proj.get('end')}",
                proj_pat(f'?p time:hasInterval ?i . ?i time:hasBeginning ?b . '
                         f'?i time:hasEnd ?e . FILTER(STR(?b) = "{proj.get("start")}") . '
                         f'FILTER(STR(?e) = "{proj.get("end")}")'))
    b.check("C05", "P5/P16/P17", "DMP dmp_id",
            f"dmpId {dmp_id!r} typed {d['dmp_id']['type']!r}",
            proj_pat(f'?p edo:dmpId ?id . ?id dcterms:identifier '
                     f'{sparql_str(dmp_id)} ; dcterms:type "{d["dmp_id"]["type"]}"'))
    b.check("C06", "P6", "DMP contact (absent)", "no edo:hasContact (faithful P6 omit)",
            "?p a edo:Project . ?p edo:hasContact ?c", expect=False)

    for contrib in d.get("contributor", []):
        name = contrib["name"].strip()
        if contrib.get("mbox"):
            b.check("C07", "P10/P11", "DMP contributor (mbox)",
                    f'agent {name!r} with mbox mailto:{contrib["mbox"]}',
                    f'?p edo:hasContribution ?c . ?c prov:agent ?a . '
                    f'?a foaf:name {sparql_str(name)} ; '
                    f'foaf:mbox "mailto:{contrib["mbox"]}"^^xsd:anyURI')
        role_raw = " / ".join(contrib.get("role", []))
        role = ROLE_FALLBACK
        for pattern, cv in ROLE_TRANSLATION:
            if pattern.search(role_raw):
                role = cv
                break
        b.check("C08", "P8", "DMP contributor role", f'{role_raw!r} -> {role!r}',
                f'?p edo:hasContribution ?c . ?c prov:agent ?a . '
                f'?a foaf:name {sparql_str(name)} . ?c dcterms:type {sparql_str(role)}')
    b.count_check("C09", "P7", "DMP contributors", "two Contribution nodes",
                  "?p edo:hasContribution ?c", expect=len(d.get("contributor", [])))

    for ds in d.get("dataset", []):
        ds_id = (ds.get("dataset_id") or {}).get("identifier")
        ds_type = (ds.get("dataset_id") or {}).get("type", "other")
        b.check("C10", "P18", "DMP dataset_id", f"{ds_id!r} typed {ds_type!r}",
                f'?p dcat:dataset ?d . ?d edo:identifier ?id . '
                f'?id dcterms:identifier {sparql_str(str(ds_id))} ; '
                f'dcterms:type "{ds_type}"')
        b.check("C11", "P19", "DMP dataset title", ds["title"],
                f'?p dcat:dataset ?d . ?d dcterms:title {sparql_str(ds["title"])}')
        if ds.get("description"):
            b.check("C12", "P20", "DMP dataset description", "carried verbatim",
                    f'?p dcat:dataset ?d . ?d dcterms:description '
                    f'{sparql_str(ds["description"])}')
        if ds.get("issued"):
            b.check("C13", "P21", "DMP dataset issued", ds["issued"],
                    f'?p dcat:dataset ?d . ?d dcterms:issued ?v . '
                    f'FILTER(STR(?v) = "{ds["issued"]}")')
        kws = ds.get("keyword", [])
        if kws:
            b.count_check("C14", "P23", "DMP dataset keywords",
                          f"{len(kws)} keywords", "?d dcat:keyword ?v", expect=len(kws))
        b.check("C15", "P24", "DMP personal_data", f"{ds.get('personal_data')!r} -> true",
                '?p dcat:dataset ?d . ?d edo:personalData ?v . FILTER(?v = true)')
        b.check("C16", "P25", "DMP sensitive_data", f"{ds.get('sensitive_data')!r} -> true",
                '?p dcat:dataset ?d . ?d edo:sensitiveData ?v . FILTER(?v = true)')
        qa = ds.get("data_quality_assurance", [])
        if qa:
            b.count_check("C17", "P26", "DMP data_quality_assurance",
                          f"{len(qa)} split items", "?d edo:qualityAssurance ?v",
                          expect=len(qa))
        if ds.get("preservation_statement"):
            b.check("C18", "P27", "DMP preservation_statement", "carried verbatim",
                    f'?d edo:preservationStatement {sparql_str(ds["preservation_statement"])}')
        if ds.get("security_and_privacy"):
            b.check("C19", "P28", "DMP security_and_privacy (documented loss)",
                    "no security predicate anywhere (P28: no v0.2 target)",
                    '?s ?p ?o . FILTER(CONTAINS(LCASE(STR(?p)), "security"))',
                    expect=False)

        dists = ds.get("distribution", [])
        if dists:
            during = dists[0]
            d_title = during.get("title", "Storage during the project")
            # access_url is optional (P32); partial exports omit it
            props = f'?x dcterms:title {sparql_str(d_title)}'
            if during.get("access_url"):
                props += f' ; dcat:accessURL <{during["access_url"]}>'
            props += f' ; edo:dataAccess "{during.get("data_access", "closed")}"'
            b.check("C20", "P31/P32/P33", "DMP distribution (during)",
                    f'title {d_title!r}, accessURL {during.get("access_url")!r}, '
                    f'dataAccess {during.get("data_access")!r}',
                    f'?p dcat:dataset ?d . ?d dcat:distribution ?x . {props}')
            formats = sorted({m for fmt in during.get("format", [])
                              for pat, m in FORMAT_TRANSLATION if pat.search(fmt)})
            if formats:
                b.count_check("C21", "P34", "DMP distribution formats",
                              f"{during.get('format')} -> {formats} (IANA IRIs)",
                              "?d dcat:distribution ?x . ?x dcat:format ?f",
                              expect=len(formats))
            if len(dists) > 1:
                after = dists[1]
                pid_values = after.get("pid_system") or []
                if isinstance(pid_values, str):
                    pid_values = [pid_values]
                b.check("C22", "P31/P33/P36", "DMP distribution (after)",
                        f'title {after.get("title")!r}, dataAccess {after.get("data_access")!r}, '
                        f'pidSystem {pid_values!r}',
                        f'?d dcat:distribution ?x . '
                        f'?x dcterms:title {sparql_str(after.get("title", "Preservation after the project"))} ; '
                        f'edo:dataAccess "{after.get("data_access", "closed")}" ; '
                        f'edo:pidSystem "{pid_values[0] if pid_values else ""}"')
                host = (after.get("host") or {}).get("title")
                if host:
                    b.check("C23", "P37/P40", "DMP distribution host",
                            f'Host node {host!r}',
                            f'?d dcat:distribution ?x . ?x edo:hostedBy ?h . '
                            f'?h a edo:Host ; dcterms:title {sparql_str(host)}')
                for lic in after.get("license", []) or []:
                    if lic.get("license_ref"):
                        b.check("C24", "P38/P39/P41/P42", "DMP distribution license",
                                f'{lic["license_ref"]} from {lic.get("start_date")}',
                                f'?d dcat:distribution ?x . ?x edo:license ?l . '
                                f'?l dcterms:license <{lic["license_ref"]}> . '
                                f'?l time:hasBeginning ?b . FILTER(STR(?b) = "{lic.get("start_date")}")')

        b.check("C25", "P30", "dataset<->sensor link (gap #18)",
                "no prov:wasGeneratedBy on this dataset (no PIDINST fragment)",
                "?p dcat:dataset ?d . ?d prov:wasGeneratedBy ?s", expect=False)

    if device:
        attrs = device["data"]["attributes"]
        b.check("C26", "S1", "SMS device short_name", attrs["short_name"],
                f'?s a sosa:Sensor . ?s dcterms:title {sparql_str(attrs["short_name"])}')
        if attrs.get("model"):
            b.check("C27", "S2", "SMS device model", attrs["model"],
                    f'?s edo:model {sparql_str(attrs["model"].strip())}')
        if attrs.get("manufacturer_name"):
            b.check("C28", "S3", "SMS manufacturer_name",
                    attrs["manufacturer_name"].strip(),
                    f'?s edo:manufacturer {sparql_str(attrs["manufacturer_name"].strip())}')
        if attrs.get("device_type_uri"):
            b.check("C29", "S4", "SMS device_type_uri", attrs["device_type_uri"],
                    f'?s dcterms:type <{attrs["device_type_uri"]}>')
        if attrs.get("persistent_identifier"):
            b.check("C30", "S5", "SMS persistent_identifier (handle)",
                    attrs["persistent_identifier"],
                    f'?s edo:identifier ?id . ?id dcterms:identifier '
                    f'{sparql_str(attrs["persistent_identifier"])} ; dcterms:type "handle"')

    for prop in properties:
        attrs_p = prop["data"]["attributes"]
        prop_uri = attrs_p["property_uri"]
        override = DATASHEET_OVERRIDES.get(prop_uri, {})
        b.check("C31", "S7", "SMS property_uri", prop_uri,
                f'?m smscv:measuredQuantity <{prop_uri}>')
        if attrs_p.get("property_name"):
            b.check("C32", "S8", "SMS property_name", attrs_p["property_name"],
                    f'?m dcterms:title {sparql_str(attrs_p["property_name"])}')
        if attrs_p.get("unit_uri"):
            b.check("C33", "S9", "SMS unit_uri", attrs_p["unit_uri"],
                    f'?m edo:unit <{attrs_p["unit_uri"]}>')
        range_min = override.get("measuring_range_min", attrs_p.get("measuring_range_min"))
        range_max = override.get("measuring_range_max", attrs_p.get("measuring_range_max"))
        b.check("C34", "S10", "SMS measuring range (datasheet override)",
                f"{range_min}…{range_max} (SMS said "
                f"{attrs_p.get('measuring_range_min')}…{attrs_p.get('measuring_range_max')})",
                f'?m edo:measuringRangeMin ?min . ?m edo:measuringRangeMax ?max . '
                f'FILTER(?min = {range_min} && ?max = {range_max})')
        if override:
            b.check("C35", "S10", "SMS measuring range (raw SMS values rejected)",
                    "SMS values -80.0/+60.0 are NOT in the graph",
                    f'?m edo:measuringRangeMin ?v . FILTER(?v = '
                    f'{attrs_p.get("measuring_range_min")})', expect=False)
        accuracy = override.get("accuracy", attrs_p.get("accuracy"))
        if accuracy is not None:
            b.check("C36", "S11", "SMS accuracy (datasheet override)", accuracy,
                    f'?m edo:accuracy {sparql_str(accuracy)}')
        resolution = override.get("resolution", attrs_p.get("resolution"))
        if resolution is not None:
            b.check("C37", "S12", "SMS resolution (datasheet override)", resolution,
                    f'?m edo:resolution ?v . FILTER(?v = {resolution})')
        if attrs_p.get("sampling_media_uri"):
            b.check("C38", "S13", "SMS sampling_media_uri", attrs_p["sampling_media_uri"],
                    f'?m smscv:samplingMedia <{attrs_p["sampling_media_uri"]}>')
        if attrs_p.get("compartment_uri"):
            b.check("C39", "S14", "SMS compartment_uri", attrs_p["compartment_uri"],
                    f'?m smscv:compartment <{attrs_p["compartment_uri"]}>')
        if attrs_p.get("aggregation_type_uri"):
            b.check("C40", "S15", "SMS aggregation_type_uri", attrs_p["aggregation_type_uri"],
                    f'?m edo:aggregationType <{attrs_p["aggregation_type_uri"]}>')

    # S16: sensor emitted as standalone node (unlinked, gap #18) is covered by
    # the sensor checks themselves; the "not linked to dataset" aspect by C25.


# ---------------------------------------------------------------------------
# SPARQL/HTTP helpers
# ---------------------------------------------------------------------------
def sparql(base_url: str, dataset: str, user: str, password: str, query: str):
    """POST a SPARQL query, return parsed JSON results (or boolean)."""
    status, body = D._req(
        "POST", f"{base_url}/{dataset}/query", user, password,
        data=query.encode("utf-8"), content_type="application/sparql-query",
        accept="application/sparql-results+json", timeout=60.0)
    if status >= 400:
        raise RuntimeError(f"SPARQL query failed (HTTP {status}): "
                           f"{body.decode(errors='replace')[:500]}")
    return json.loads(body)


def sparql_update(base_url: str, dataset: str, user: str, password: str,
                  update: str) -> None:
    D._req("POST", f"{base_url}/{dataset}/update", user, password,
           data=update.encode("utf-8"), content_type="application/sparql-update")


def ask(base_url, dataset, user, password, pattern: str, graph: str | None) -> bool:
    body = f"GRAPH <{graph}> {{ {pattern} }}" if graph else pattern
    result = sparql(base_url, dataset, user, password,
                    SPARQL_PREFIXES + f"ASK {{ {body} }}")
    return bool(result.get("boolean"))


def count(base_url, dataset, user, password, pattern: str, graph: str | None) -> int:
    body = f"GRAPH <{graph}> {{ {pattern} }}" if graph else pattern
    result = sparql(base_url, dataset, user, password,
                    SPARQL_PREFIXES + f"SELECT (COUNT(*) AS ?n) WHERE {{ {body} }}")
    bindings = result.get("results", {}).get("bindings", [])
    return int(bindings[0]["n"]["value"]) if bindings else 0


def shacl_validate(graph_file: Path, shapes_file: Path) -> dict:
    """Validate host-side with pyshacl (README's authoritative invocation)."""
    if shutil.which("pyshacl") is not None:
        cmd = ["pyshacl"]
    else:
        # venv installs put the console script on the venv's bin/ only; run
        # the module through the same interpreter the tool runs under.
        try:
            import importlib
            importlib.import_module("pyshacl")
            cmd = [sys.executable, "-m", "pyshacl"]
        except ImportError:
            return {"ran": False, "note": "pyshacl not available — validation "
                                          "skipped (install host-side: pip install pyshacl)"}
    proc = subprocess.run(
        [*cmd, "-s", str(shapes_file), "-d", str(graph_file),
         "-e", str(shapes_file)],
        capture_output=True, text=True, timeout=300)
    # pyshacl writes the human-readable validation report to stdout (small) and
    # verbose progress logs to stderr (large) — report on stdout wins.
    stdout = (proc.stdout or "").strip()
    excerpt = stdout or (proc.stderr or "").strip()[-2000:]
    conforms = stdout.startswith("Validation Report") and "Conforms: True" in stdout
    return {"ran": True, "conforms": conforms, "returncode": proc.returncode,
            "output": excerpt[:4000]}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _default_property_files() -> tuple[Path, ...]:
    files = sorted(SMS_DIR.glob("device-*-property-*.json"))
    return tuple(files) if files else ()


def _latest_artifacts_dir() -> Path | None:
    if not TRIP_DIR.exists():
        return None
    dirs = sorted(p for p in TRIP_DIR.iterdir() if p.is_dir())
    return dirs[-1] if dirs else None


@click.group("trip")
@click.option("--port", default=3031, type=int, show_default=True,
              help="Fuseki HTTP port (host side).")
@click.option("--user", default="admin", show_default=True, help="Fuseki admin user.")
@click.option("--password", default="edo-proto", show_default=True,
              help="Fuseki admin password.")
@click.option("--dataset", default="projects", show_default=True,
              help="Fuseki dataset for the instance graph.")
@click.pass_context
def trip(ctx, port, user, password, dataset):
    """CF2-003 round trip: transform -> store -> dump -> verify.

    Realises the three acceptance scenarios of card CF2-003 against the
    maDMP export Measurement_02-13.json and the SMS device-67 record;
    see scripts/trafos/README.md for the full documentation.
    """
    ctx.obj = {
        "base_url": f"http://127.0.0.1:{port}",
        "user": user, "password": password, "dataset": dataset,
    }


@trip.command("transform")
@click.option("--dmp", "dmp_path", type=click.Path(exists=True, dir_okay=False),
              default=str(DMP_DEFAULT), show_default=True,
              help="maDMP export (JSON) to transform.")
@click.option("--sms-device", "device_path", type=click.Path(exists=True, dir_okay=False),
              default=str(DEVICE_DEFAULT), show_default=True,
              help="SMS device JSON:API record.")
@click.option("--sms-property", "property_paths", multiple=True,
              type=click.Path(exists=True, dir_okay=False),
              default=[str(p) for p in _default_property_files()],
              show_default="(all device-*-property-*.json under scripts/sms/)",
              help="SMS device-property JSON records (repeatable).")
@click.option("--out", "out_dir", type=click.Path(file_okay=False), default=None,
              help="Artifacts directory (default: data/trip/<timestamp>).")
@click.pass_obj
def transform_cmd(obj, dmp_path, device_path, property_paths, out_dir):
    """Scenario 1: apply the mapping catalogue and emit the internal-format graph."""
    out = Path(out_dir) if out_dir else TRIP_DIR / _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    dmp = _load_json(Path(dmp_path))
    device = _load_json(Path(device_path)) if device_path else None
    properties = [_load_json(Path(p)) for p in property_paths]
    turtle, checks, meta = transform(dmp, device, properties)
    (out / "project-graph.ttl").write_text(turtle, encoding="utf-8")
    report = {
        "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
        "inputs": {"dmp": str(dmp_path), "sms_device": str(device_path),
                   "sms_properties": list(property_paths)},
        "stages": {"transform": {"project_iri": meta["project_iri"],
                                 "sensor_iri": meta["sensor_iri"],
                                 "applied_rules": meta["rules"],
                                 "notes": meta["notes"]}},
        "checks": [{"id": c["id"], "rule": c["rule"], "description": c["description"],
                    "kind": c["kind"]} for c in checks],
    }
    (out / "trip-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    click.echo(f"Transformed {Path(dmp_path).name} + SMS "
               f"({len(meta['rules'])} rule applications, {len(meta['notes'])} notes, "
               f"{len(checks)} checks prepared).")
    for note in meta["notes"]:
        click.echo(f"  NOTE: {note}")
    click.echo(f"Graph written to {out / 'project-graph.ttl'}")


@trip.command("store")
@click.option("--graph", "graph_path", type=click.Path(exists=True, dir_okay=False),
              default=None, help="Graph to store (default: latest trip artifacts).")
@click.option("--wipe/--no-wipe", default=True, show_default=True,
              help="CLEAR the dataset default graph before loading (destructive).")
@click.option("--validate/--no-validate", default=True, show_default=True,
              help="Validate the stored graph with pyshacl (if available).")
@click.pass_obj
def store_cmd(obj, graph_path, wipe, validate):
    """Scenario 2: store the transformed project in the /projects dataset."""
    base, ds, user, password = (obj["base_url"], obj["dataset"],
                                obj["user"], obj["password"])
    graph = Path(graph_path) if graph_path else None
    if graph is None:
        latest = _latest_artifacts_dir()
        if not latest:
            raise click.ClickException("No trip artifacts found — run "
                                       "`fuseki-proto trip transform` first.")
        graph = latest / "project-graph.ttl"

    if wipe:
        sparql_update(base, ds, user, password, "CLEAR DEFAULT")
        click.echo(f"Cleared default graph of /{ds}.")
    D.http_upload(f"{base}/{ds}/data", user, password, graph,
                  content_type="text/turtle")
    click.echo(f"Loaded {graph.name} into /{ds} (default graph).")

    # retrievability: the project must be queryable again
    result = sparql(base, ds, user, password, SPARQL_PREFIXES +
                    "SELECT ?title ?dmpId WHERE { ?p a edo:Project ; "
                    "dcterms:title ?title ; edo:dmpId ?id . "
                    "?id dcterms:identifier ?dmpId }")
    rows = result.get("results", {}).get("bindings", [])
    if not rows:
        raise click.ClickException("Stored graph is NOT retrievable — no "
                                   "edo:Project found via /query.")
    row = rows[0]
    title = row["title"]["value"]
    dmp_id = row["dmpId"]["value"]
    click.echo(f"Retrievable via /{ds}/query: project {title!r} "
               f"(dmp_id {dmp_id!r}).")
    triples = count(base, ds, user, password, "?s ?p ?o", None)
    click.echo(f"Default graph now holds {triples} triples.")

    shacl = {"ran": False}
    if validate:
        shacl = shacl_validate(graph, SHAPES_FILE)
        if shacl.get("ran"):
            if shacl["conforms"]:
                click.echo("SHACL: graph CONFORMS to project-claim-shapes.ttl.")
            else:
                click.echo("SHACL: graph does NOT conform — violations reported below.")
                click.echo(shacl.get("output", ""))
        else:
            click.echo(f"SHACL: skipped ({shacl.get('note')})")

    _patch_latest_report({"stages": {"store": {
        "graph": str(graph), "triples": triples,
        "retrievable": {"title": title, "dmp_id": dmp_id},
        "shacl": {k: v for k, v in shacl.items() if k != "output"} | (
            {"output_tail": shacl.get("output", "")} if shacl.get("ran") else {})}}})


@trip.command("verify")
@click.option("--dmp", "dmp_path", type=click.Path(exists=True, dir_okay=False),
              default=str(DMP_DEFAULT), show_default=True)
@click.option("--sms-device", "device_path", type=click.Path(exists=True, dir_okay=False),
              default=str(DEVICE_DEFAULT), show_default=True)
@click.option("--sms-property", "property_paths", multiple=True,
              type=click.Path(exists=True, dir_okay=False),
              default=[str(p) for p in _default_property_files()],
              show_default="(all device-*-property-*.json under scripts/sms/)")
@click.pass_obj
def verify_cmd(obj, dmp_path, device_path, property_paths):
    """Scenario 3: dump /projects and verify field-level equality with the sources."""
    base, ds, user, password = (obj["base_url"], obj["dataset"],
                                obj["user"], obj["password"])
    latest = _latest_artifacts_dir()
    if not latest:
        raise click.ClickException("No trip artifacts found — run "
                                   "`fuseki-proto trip transform` first.")

    dmp = _load_json(Path(dmp_path))
    device = _load_json(Path(device_path)) if device_path else None
    properties = [_load_json(Path(p)) for p in property_paths]
    _, checks, meta = transform(dmp, device, properties)

    # 1. dump the stored graph back out
    dump = D.dump_graph(base, ds, user, password)
    dump_path = latest / "roundtrip-dump.ttl"
    dump_path.write_bytes(dump)
    click.echo(f"Dumped /{ds} -> {dump_path} ({len(dump)} bytes).")

    # 2. replay the dump into a named graph (what Fuseki served must parse
    #    and re-load — the dump is the round-trip artifact under test)
    sparql_update(base, ds, user, password,
                  f"DROP SILENT GRAPH <{REPLAY_GRAPH}>")
    D._req("POST", f"{base}/{ds}/data?graph={urllib.parse.quote(REPLAY_GRAPH, safe='')}",
           user, password, data=dump, content_type="text/turtle", timeout=120.0)
    replay_triples = count(base, ds, user, password, "?s ?p ?o", REPLAY_GRAPH)
    default_triples = count(base, ds, user, password, "?s ?p ?o", None)
    click.echo(f"Re-uploaded dump into <{REPLAY_GRAPH}> "
               f"({replay_triples} triples; default graph: {default_triples}).")

    # 3. field-level checks: against the replay graph (the dump) AND the
    #    default graph (the store)
    results = []
    for check in checks:
        pattern = check["pattern"]
        replay = ask(base, ds, user, password, pattern, REPLAY_GRAPH)
        default = ask(base, ds, user, password, pattern, None)
        passed = (replay == (check["kind"] != "absent")) and \
                 (default == (check["kind"] != "absent"))
        results.append({**{k: v for k, v in check.items() if k != "pattern"},
                        "result": {"replay": replay, "default": default},
                        "pass": passed})

    counts_equal = replay_triples == default_triples
    passed_n = sum(1 for r in results if r["pass"])
    failed = [r for r in results if not r["pass"]]

    click.echo("")
    click.echo(f"Round-trip checks: {passed_n}/{len(results)} passed "
               f"(replay graph vs. original DMP/SMS sources).")
    for r in failed:
        click.echo(f"  FAIL [{r['id']}] ({r['rule']}) {r['description']}: "
                   f"replay={r['result']['replay']} default={r['result']['default']}")
    click.echo(f"Triple-count equality default vs. replay: "
               f"{'OK' if counts_equal else 'MISMATCH'} "
               f"({default_triples} vs. {replay_triples}).")

    report_path = latest / "trip-report.json"
    report = {}
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    report.setdefault("stages", {})["verify"] = {
        "dump": str(dump_path), "replay_graph": REPLAY_GRAPH,
        "triple_counts": {"default": default_triples, "replay": replay_triples,
                          "equal": counts_equal},
        "summary": {"total": len(results), "passed": passed_n, "failed": len(failed)},
    }
    report["checks"] = results
    report["summary"] = {"total": len(results), "passed": passed_n,
                         "failed": len(failed), "triple_counts_equal": counts_equal}
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    click.echo(f"Report updated: {report_path}")

    if failed or not counts_equal:
        raise SystemExit(1)


@trip.command("run")
@click.pass_context
def run_cmd(ctx):
    """All three scenarios: transform -> store -> verify."""
    ctx.invoke(transform_cmd)
    ctx.invoke(store_cmd)
    ctx.invoke(verify_cmd)


def _patch_latest_report(patch: dict) -> None:
    latest = _latest_artifacts_dir()
    path = latest / "trip-report.json" if latest else None
    if not path or not path.exists():
        return
    report = json.loads(path.read_text(encoding="utf-8"))
    for key, value in patch.items():
        if isinstance(value, dict):
            report.setdefault(key, {}).update(value)
        else:
            report[key] = value
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                    encoding="utf-8")


if __name__ == "__main__":
    trip()
