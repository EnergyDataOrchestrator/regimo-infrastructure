#!/usr/bin/env python
"""04_P04_S04 — traceable validation of the maDMP export plugin (card CF1-004).

Retraceable procedure: every step of a validation run writes an artefact into
`measurement_02/`, so a run can be reconstructed and audited later:

  1. ground truth  -> Measurement_02-groundtruth.json
     All current answers of the RDMO project (attribute path, set, text,
     raw value, option uri_path) as dumped from the instance DB.
  2. render        -> Measurement_02.render.json
     get_dmp() of the *deployed* plugin (`rdmo_madmp.exports.MaDMPExport`)
     against the same project — the same code path the RDMO UI export uses.
  3. trace matrix  -> validation-report.md
     (a) every mapping-spec leaf: does the attribute exist in the catalog,
         is it answered, which value resolved, does it appear in the render;
     (b) every answered project value that did NOT make it into the render
         (answered-but-not-exported gaps);
     (c) structural conformance checks against madmp-lightmodel.yaml
         (required slots, yes/no/unknown enums, object shapes).

Usage (inside the RDMO env):

    /Users/ot2661/Servers/rdmo-app/env/bin/python 04_P04_S04_validate-export.py \
        [--project 4] [--ui-json measurement_02/Measurement_02-dmp.json]

`--ui-json` additionally compares a UI-downloaded export with the offline
render (byte comparison) to close the loop end-to-end.
"""

import argparse
import json
import os
import sys
from pathlib import Path

RDMO_APP = '/Users/ot2661/Servers/rdmo-app'
OUT_DIR = Path(__file__).resolve().parent / 'measurement_02'

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, RDMO_APP)
os.chdir(RDMO_APP)  # db.sqlite3 path is relative to the rdmo-app dir

import django  # noqa: E402

django.setup()

import yaml  # noqa: E402
from django.utils import timezone  # noqa: E402
from rdmo.domain.models import Attribute  # noqa: E402
from rdmo.projects.models import Project, Value  # noqa: E402
from rdmo_madmp.exports import MaDMPExport  # noqa: E402

HERE = Path(__file__).resolve().parent
MAPPING_FILE = HERE / '03_P03_S03_madmp-export.mapping.yaml'
LIGHTMODEL_FILE = HERE / 'madmp-lightmodel.yaml'

YES_NO_UNKNOWN = {'yes', 'no', 'unknown'}


# ---------------------------------------------------------------------------
# step 1: ground truth
# ---------------------------------------------------------------------------

def dump_ground_truth(project):
    rows = []
    values = (Value.objects.filter(project=project, snapshot=None)
              .select_related('attribute', 'option'))
    for v in values.order_by('attribute__path', 'set_index', 'collection_index'):
        rows.append({
            'attribute': v.attribute.path if v.attribute else None,
            'set_prefix': v.set_prefix or '',
            'set_index': v.set_index,
            'collection_index': v.collection_index,
            'text': v.text,
            'value': v.value,
            'option': v.option.uri_path if v.option else None,
        })
    return {
        'project_id': project.id,
        'project_title': project.title,
        'dumped': timezone.now().isoformat(),
        'answers': rows,
    }


# ---------------------------------------------------------------------------
# step 2: render via the deployed plugin
# ---------------------------------------------------------------------------

def render_dmp(project):
    export = MaDMPExport('madmp', 'as maDMP', 'rdmo_madmp.exports.MaDMPExport')
    export.project = project
    return export.get_dmp()


# ---------------------------------------------------------------------------
# step 3a: traceability matrix over the mapping spec
# ---------------------------------------------------------------------------

def iter_leaf_specs(node, location='mapping'):
    """Yield (location, spec) for every leaf spec carrying a lookup."""
    if isinstance(node, list):
        for i, item in enumerate(node):
            yield from iter_leaf_specs(item, f'{location}[{i}]')
    elif isinstance(node, dict):
        if any(k in node for k in ('attribute', 'project_field', 'base_attribute')):
            yield location, node
            return  # leaf specs do not nest further lookups
        for key, value in node.items():
            yield from iter_leaf_specs(value, f'{location}/{key}')


def person_paths(spec):
    base = spec['base_attribute']
    name_suffix = spec.get('name_suffix', 'name')
    mbox_suffix = spec.get('mbox_suffix', 'mbox')
    identifier_suffix = spec.get('identifier_suffix', 'identifier')
    return [
        ('name', f'{base}/{name_suffix}', None),
        ('mbox', f'{base}/{mbox_suffix}', None),
        ('identifier', f'{base}/{identifier_suffix}', None),
        ('identifier_type', f'{base}/{identifier_suffix}_type', 'person_id_type_options'),
    ]


def trace_matrix(export, dmp, mapping):
    dmp_text = json.dumps(dmp, ensure_ascii=False)
    rows = []

    def answered(path):
        return (Value.objects.filter(project=export.project, snapshot=None,
                                     attribute__path=path)
                .select_related('option'))

    def row(location, kind, path, option_map=None, set_index=0, label='', leaf=None):
        exists = Attribute.objects.filter(path=path).exists() if path else False
        values = list(answered(path)) if path else []
        texts = [v.text for v in values if v.text]
        option_uri_paths = [v.option.uri_path for v in values if v.option]

        resolved = None
        try:
            if leaf is not None:
                if 'options' in leaf:
                    resolved = export.resolve_option(leaf, set_index=set_index)
                else:
                    resolved = export.resolve(leaf, set_index=set_index)
            else:
                spec = {'attribute': path}
                if option_map is not None:
                    resolved = export.resolve_option(
                        {'attribute': path, 'options': option_map}, set_index=set_index)
                else:
                    resolved = export.resolve(spec, set_index=set_index)
        except Exception as exc:  # report, don't die
            resolved = f'<error: {exc}>'

        # presence in the rendered output: the resolved term/value as string.
        # Booleans are exported by the renderer as "yes"/"no", so compare in
        # that (quoted, JSON-value) form instead of the raw True/False.
        if isinstance(resolved, bool):
            display = 'yes' if resolved else 'no'
            present = f'"{display}"' in dmp_text
        else:
            present = bool(resolved is not None and
                           (isinstance(resolved, (int, float)) or str(resolved)) and
                           (json.dumps(resolved, ensure_ascii=False).strip('"') in dmp_text
                            or str(resolved) in dmp_text))

        status = 'OK'
        if not exists:
            status = 'PATH-MISSING-IN-CATALOG'
        elif not values:
            status = 'NOT-ANSWERED'
        elif resolved is None:
            status = 'RESOLVED-EMPTY'
        elif not present:
            status = 'NOT-IN-OUTPUT'

        rows.append({
            'mapping_location': location,
            'kind': kind,
            'label': label,
            'rdmo_path': path,
            'option_map': option_map or '',
            'in_catalog': exists,
            'answered': bool(values),
            'answer_texts': texts[:5],
            'answer_option_uris': option_uri_paths[:5],
            'resolved': resolved,
            'in_output': present,
            'status': status,
        })

    dmp_spec = mapping.get('dmp', {})

    # title (template or attribute), created/modified (project fields)
    title_spec = dmp_spec.get('title', {})
    if 'attribute' in title_spec:
        row('dmp/title', 'attribute', title_spec['attribute'])
    else:
        rows.append({
            'mapping_location': 'dmp/title', 'kind': 'template',
            'label': title_spec.get('template', ''), 'rdmo_path': '(project title)',
            'in_catalog': '', 'answered': '', 'answer_texts': [],
            'answer_option_uris': [], 'resolved': dmp.get('title'),
            'in_output': 'title' in dmp, 'status': 'OK' if 'title' in dmp else 'NOT-IN-OUTPUT',
        })
    for key in ('created', 'modified'):
        spec = dmp_spec.get(key, {})
        if 'project_field' in spec:
            rows.append({
                'mapping_location': f'dmp/{key}', 'kind': 'project_field',
                'label': spec['project_field'], 'rdmo_path': f'project.{spec["project_field"]}',
                'in_catalog': '', 'answered': '', 'answer_texts': [],
                'answer_option_uris': [], 'resolved': dmp.get(key),
                'in_output': key in dmp, 'status': 'OK' if key in dmp else 'NOT-IN-OUTPUT',
            })

    # contact + contributor person specs
    contact_spec = dmp_spec.get('contact')
    if contact_spec:
        for slot, path, option_map in person_paths(contact_spec):
            row(f'dmp/contact/{slot}', 'person', path, option_map)
    for i, spec in enumerate(dmp_spec.get('contributor', [])):
        set_note = f' (set: {spec["set"]})' if spec.get('set') else ''
        for slot, path, option_map in person_paths(spec):
            row(f'dmp/contributor[{i}]/{slot}{set_note}', 'person', path, option_map)

    # cost specs
    for i, spec in enumerate(dmp_spec.get('cost', [])):
        row(f'dmp/cost[{i}] "{spec.get("title")}"', 'cost', spec.get('attribute'))

    # dmp_id identifier spec — generated (no catalog path; gap register #6)
    dmp_id_spec = dmp_spec.get('dmp_id') or {}
    dmp_id_out = dmp.get('dmp_id') or {}
    for slot in ('identifier', 'type'):
        spec = dmp_id_spec.get(slot)
        if not spec:
            continue
        if 'generated' in spec or 'fixed' in spec:
            kind = 'generated' if 'generated' in spec else 'fixed'
            detail = spec.get('generated') or spec.get('fixed')
            extra = f' (seed: {spec["seed"]})' if spec.get('seed') else ''
            rows.append({
                'mapping_location': f'dmp/dmp_id/{slot}', 'kind': kind,
                'label': f'{detail}{extra}', 'rdmo_path': f'({kind})',
                'in_catalog': '', 'answered': '', 'answer_texts': [],
                'answer_option_uris': [], 'resolved': dmp_id_out.get(slot),
                'in_output': slot in dmp_id_out,
                'status': 'OK' if slot in dmp_id_out else 'NOT-IN-OUTPUT',
            })
        else:
            row(f'dmp/dmp_id/{slot}', 'attribute-option',
                spec.get('attribute'), spec.get('options'))

    # language
    spec = dmp_spec.get('language')
    if spec:
        row('dmp/language', 'attribute-option', spec.get('attribute'), spec.get('options'))

    # project spec
    for slot in ('start', 'end', 'title', 'description'):
        spec = (dmp_spec.get('project') or {}).get(slot)
        if spec:
            if 'project_field' in spec:
                rows.append({
                    'mapping_location': f'dmp/project/{slot}', 'kind': 'project_field',
                    'label': spec['project_field'],
                    'rdmo_path': f'project.{spec["project_field"]}',
                    'in_catalog': '', 'answered': '', 'answer_texts': [],
                    'answer_option_uris': [], 'resolved': (dmp.get('project') or [{}])[0].get(slot),
                    'in_output': slot in (dmp.get('project') or [{}])[0],
                    'status': 'OK' if slot in (dmp.get('project') or [{}])[0] else 'NOT-IN-OUTPUT',
                })
            else:
                row(f'dmp/project/{slot}', 'attribute',
                    spec.get('attribute'), spec.get('options'))

    # dataset fields
    fields = (mapping.get('dataset') or {}).get('fields', {})
    for name, spec in fields.items():
        if name in ('dataset_id', 'distribution'):
            continue
        if isinstance(spec, list):  # security_and_privacy
            for i, sub in enumerate(spec):
                row(f'dataset/fields/{name}[{i}] "{sub.get("title")}"',
                    'attribute', sub.get('attribute'))
        elif isinstance(spec, dict):
            row(f'dataset/fields/{name}', 'attribute-option',
                spec.get('attribute'), spec.get('options'), leaf=spec)

    # dataset_id identifier spec
    for slot in ('identifier', 'type', 'fallback_identifier'):
        spec = (fields.get('dataset_id') or {}).get(slot)
        if spec:
            row(f'dataset/fields/dataset_id/{slot}', 'attribute-option',
                spec.get('attribute'), spec.get('options'))

    # distributions (during / after)
    distribution = fields.get('distribution', {})
    for phase in ('during', 'after'):
        for name, spec in (distribution.get(phase) or {}).items():
            if name == 'title':
                continue
            row(f'dataset/fields/distribution/{phase}/{name}',
                'attribute-option', spec.get('attribute'), spec.get('options'),
                leaf=spec)

    return rows


# ---------------------------------------------------------------------------
# step 3b: answered-but-not-exported gaps
# ---------------------------------------------------------------------------

def export_gaps(dmp, ground_truth, rows, option_map_keys=()):
    dmp_text = json.dumps(dmp, ensure_ascii=False)
    # A value may be exported *transformed* (e.g. an option map turns
    # 'Yes, externally for everyone' into 'open'), in which case the verbatim
    # text check below would false-positive. The trace matrix is authoritative:
    # if its row for this path reports in_output, the answer made it out.
    exported_paths = {r['rdmo_path'] for r in rows if r['in_output']}
    mapped_paths = {r['rdmo_path'] for r in rows}
    gaps = []
    for a in ground_truth['answers']:
        if not a['text'] or a['attribute'] in exported_paths:
            continue
        if a['attribute'] in mapped_paths:
            note = 'MAPPED-BUT-MISSING-IN-OUTPUT'
        else:
            note = 'no mapping spec (not part of the maDMP export)'
        if a['option'] and a['option'] not in option_map_keys:
            note += ' | option not in any option map'
        gaps.append({**a, 'note': note})
    return gaps


# ---------------------------------------------------------------------------
# step 3c: structural conformance vs madmp-lightmodel
# ---------------------------------------------------------------------------

def schema_checks(dmp):
    checks = []

    def check(name, ok, detail=''):
        checks.append({'check': name, 'ok': bool(ok), 'detail': detail})

    check('tree root object has "dmp"', isinstance(dmp, dict) and 'dmp' in dmp)
    d = dmp.get('dmp', {})

    check('dmp/title required and non-empty', bool(d.get('title')))
    for key in ('created', 'modified'):
        val = d.get(key)
        check(f'dmp/{key} is ISO-8601 timestamp', bool(val) and 'T' in str(val), str(val))

    contact = d.get('contact')
    if contact is not None:
        check('dmp/contact has name (str)', isinstance(contact, dict) and isinstance(contact.get('name'), str))
        check('dmp/contact mbox absent or str',
              contact.get('mbox') is None or isinstance(contact.get('mbox'), str))

    contributors = d.get('contributor', [])
    check('dmp/contributor is a list (if present)',
          contributors == [] or isinstance(contributors, list))
    for i, c in enumerate(contributors):
        check(f'dmp/contributor[{i}] has name (str)', isinstance(c.get('name'), str))
        roles = c.get('role', [])
        check(f'dmp/contributor[{i}].role is list of str',
              isinstance(roles, list) and all(isinstance(r, str) for r in roles))

    costs = d.get('cost', [])
    for i, c in enumerate(costs):
        check(f'dmp/cost[{i}] has title and numeric value',
              isinstance(c.get('title'), str) and isinstance(c.get('value'), (int, float)))

    datasets = d.get('dataset', [])
    check('dmp/dataset is a list', isinstance(datasets, list))
    for i, ds in enumerate(datasets):
        check(f'dmp/dataset[{i}] has title (str)', isinstance(ds.get('title'), str))
        for key in ('personal_data', 'sensitive_data'):
            val = ds.get(key)
            check(f'dmp/dataset[{i}].{key} in {sorted(YES_NO_UNKNOWN)}',
                  val in YES_NO_UNKNOWN, str(val))
        dsid = ds.get('dataset_id')
        if dsid is not None:
            check(f'dmp/dataset[{i}].dataset_id has identifier (str)',
                  isinstance(dsid.get('identifier'), str))
            check(f'dmp/dataset[{i}].dataset_id.type in {sorted(YES_NO_UNKNOWN)}'
                  if False else f'dmp/dataset[{i}].dataset_id.type present',
                  isinstance(dsid.get('type'), str), str(dsid.get('type')))
        dists = ds.get('distribution', [])
        check(f'dmp/dataset[{i}].distribution is a list', isinstance(dists, list))
        for j, dist in enumerate(dists):
            check(f'dmp/dataset[{i}].distribution[{j}] has title (str)',
                  isinstance(dist.get('title'), str))
            da = dist.get('data_access')
            check(f'dmp/dataset[{i}].distribution[{j}].data_access in open|shared|closed|external',
                  da in {'open', 'shared', 'closed', 'external'}, str(da))

    return checks


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def write_report(path, ground_truth, rows, gaps, checks, render_identical, ui_file):
    lines = []
    lines.append(f'# maDMP export validation report — project {ground_truth["project_id"]} '
                 f'"{ground_truth["project_title"]}"')
    lines.append('')
    lines.append(f'*Run:* {ground_truth["dumped"]} · '
                 f'*plugin:* deployed `rdmo_madmp.exports.MaDMPExport` · '
                 f'*mapping:* `03_P03_S03_madmp-export.mapping.yaml`')
    lines.append('')
    lines.append('Artifacts of this run: `Measurement_02-groundtruth.json` (answers), '
                 '`Measurement_02.render.json` (plugin render), this report.')
    lines.append('')

    # summary
    counts = {}
    for r in rows:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    lines.append('## Summary')
    lines.append('')
    lines.append('- mapping-spec rows: ' + str(len(rows)))
    for status, n in sorted(counts.items()):
        lines.append(f'- `{status}`: {n}')
    lines.append(f'- answered-but-not-exported values: {len(gaps)}')
    lines.append(f'- structural checks: {sum(1 for c in checks if c["ok"])}/{len(checks)} passed')
    if ui_file:
        lines.append(f'- UI export `{ui_file}` vs. offline render: '
                     + ('IDENTICAL' if render_identical else 'DIFFERENT (re-download the UI export after redeploying)'))
    lines.append('')

    # matrix
    lines.append('## Traceability matrix (mapping spec -> RDMO -> maDMP)')
    lines.append('')
    lines.append('| location | rdmo path | in catalog | answered | resolved | in output | status |')
    lines.append('|---|---|---|---|---|---|---|')
    for r in rows:
        resolved = r['resolved']
        if isinstance(resolved, (list, dict)):
            resolved = json.dumps(resolved, ensure_ascii=False)
        lines.append('| `{}` | `{}` | {} | {} | `{}` | {} | **{}** |'.format(
            r['mapping_location'], r['rdmo_path'],
            r['in_catalog'], r['answered'],
            str(resolved)[:60].replace('|', '\\|').replace('\n', ' '),
            r['in_output'], r['status']))
    lines.append('')

    # gaps
    lines.append('## Answered but not exported (candidate gaps)')
    lines.append('')
    if gaps:
        lines.append('| attribute | set_index | text | note |')
        lines.append('|---|---|---|---|')
        for g in gaps:
            note = g.get('note', '')
            lines.append('| `{}` | {} | {} | {} |'.format(
                g['attribute'], g['set_index'],
                str(g['text'])[:80].replace('|', '\\|'), note))
    else:
        lines.append('_None — every answered value appears in the render._')
    lines.append('')

    # structural checks
    lines.append('## Structural checks (madmp-lightmodel conformance)')
    lines.append('')
    lines.append('| check | ok | detail |')
    lines.append('|---|---|---|')
    for c in checks:
        lines.append('| {} | {} | {} |'.format(
            c['check'], '✅' if c['ok'] else '❌', c['detail']))
    lines.append('')
    lines.append('Note: the plugin emits the full RDA maDMP shape (contributor, cost, '
                 'project, …); `madmp-lightmodel.yaml` is the EDO target subset, so '
                 'unknown top-level keys are expected and not flagged here.')

    path.write_text('\n'.join(lines), encoding='utf-8')


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=int, default=4)
    parser.add_argument('--ui-json', type=str, default=None,
                        help='path to a UI-downloaded export for comparison')
    args = parser.parse_args()

    OUT_DIR.mkdir(exist_ok=True)

    project = Project.objects.get(id=args.project)

    # 1. ground truth
    ground_truth = dump_ground_truth(project)
    gt_path = OUT_DIR / 'Measurement_02-groundtruth.json'
    gt_path.write_text(json.dumps(ground_truth, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(f'[1/4] ground truth: {gt_path} ({len(ground_truth["answers"])} answers)')

    # 2. render
    dmp = render_dmp(project)
    render_path = OUT_DIR / 'Measurement_02.render.json'
    render_path.write_text(json.dumps({'dmp': dmp}, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(f'[2/4] render: {render_path}')

    render_identical = None
    ui_file = None
    if args.ui_json:
        ui_path = Path(args.ui_json)
        if ui_path.exists():
            ui_file = ui_path.name
            try:
                ui_obj = json.loads(ui_path.read_text(encoding='utf-8'))
                render_identical = json.loads(json.dumps({'dmp': dmp}, ensure_ascii=False, default=str)) == ui_obj
            except Exception as exc:
                print(f'      ui-json comparison failed: {exc}')
        else:
            print(f'      ui-json not found: {ui_path}')

    # 3. trace matrix + gaps + structural checks
    with open(MAPPING_FILE, encoding='utf-8') as f:
        mapping = yaml.safe_load(f)
    export = MaDMPExport('madmp', 'as maDMP', 'rdmo_madmp.exports.MaDMPExport')
    export.project = project
    rows = trace_matrix(export, dmp, mapping)
    option_map_keys = {
        key
        for option_map in mapping.get('options', {}).values()
        if isinstance(option_map, dict)
        for key in option_map
    }
    gaps = export_gaps(dmp, ground_truth, rows, option_map_keys)
    checks = schema_checks({'dmp': dmp})

    # 4. report
    report_path = OUT_DIR / 'validation-report.md'
    write_report(report_path, ground_truth, rows, gaps, checks, render_identical, ui_file)
    print(f'[3/4] trace matrix: {len(rows)} rows, gaps: {len(gaps)}, '
          f'structural: {sum(1 for c in checks if c["ok"])}/{len(checks)} passed')
    print(f'[4/4] report: {report_path}')


if __name__ == '__main__':
    main()
