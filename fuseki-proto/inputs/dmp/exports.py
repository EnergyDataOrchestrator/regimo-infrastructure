"""EDO maDMP export plugin for RDMO (card CF1-004, fragment 02_DMP_Erstellung).

This is the in-RDMO variant of the EDO maDMP production: it renders an RDMO
project (including snapshots) as maDMP JSON directly from RDMO, next to the
offline pipeline (`answers_to_dmp.py` + `02_P02_S02_madmp-mapping.transform.yaml`).

Following the EDO principle "intelligence in YAML, generic driver", all RDMO
attribute paths, option maps (controlled-vocabulary translations), titles and
role templates live in the declarative mapping spec

    03_P03_S03_madmp-export.mapping.yaml

next to this file. This module only realises the export functions (`render`,
`get_dmp`, `get_person`, `get_cost`, `get_dataset`) against that spec, using
the helper methods of the RDMO `Export` base class (`get_text`, `get_list`,
`get_set`, `get_value`, `get_option`, `get_timestamp`, `get_bool`).

To bind the plugin to a different RDMO catalog, edit the mapping spec (or set
`MaDMPExport.mapping_file`); no code changes are required.

The plugin is registered in the RDMO instance via `config/settings/local.py`:

    PROJECT_EXPORTS += [
        ('madmp', _('as maDMP'), 'rdmo_madmp.exports.MaDMPExport'),
    ]
"""

import json
from collections import defaultdict
from pathlib import Path

import yaml
from django.conf import settings
from django.http import HttpResponse

from rdmo.projects.exports import Export

BASE_DIR = Path(__file__).resolve().parent
MAPPING_FILE = BASE_DIR / '03_P03_S03_madmp-export.mapping.yaml'


class MaDMPExport(Export):

    #: Declarative mapping spec (RDMO catalog -> maDMP), see module docstring.
    mapping_file = MAPPING_FILE

    yes_no_unknown = {
        True: 'yes',
        False: 'no',
        None: 'unknown'
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        with open(self.mapping_file, encoding='utf-8') as f:
            self.mapping = yaml.safe_load(f)
        self.options = self.mapping.get('options', {})

    # ------------------------------------------------------------------
    # Leaf-spec resolution
    # ------------------------------------------------------------------

    def resolve(self, spec, set_index=0):
        """Resolve a leaf mapping spec against the project's answers."""
        if not spec:
            return None

        if 'project_field' in spec:
            return getattr(self.project, spec['project_field'], None)

        attribute = spec.get('attribute')
        extract = spec.get('extract', 'text')
        if extract == 'text':
            return self.get_text(attribute, set_index=set_index)
        elif extract == 'list':
            return self.get_list(attribute, set_index=set_index)
        elif extract == 'bool':
            return self.get_bool(attribute, set_index=set_index)
        elif extract == 'timestamp':
            return self.get_timestamp(attribute, set_index=set_index)
        elif extract == 'value':
            value = self.get_value(attribute, set_index=set_index)
            return value.value if value else None
        else:
            raise ValueError(f'Unknown extract kind: {extract}')

    def resolve_option(self, spec, set_index=0):
        """Resolve an `{attribute, options, default}` spec via an option map."""
        if not spec:
            return None

        option_map = self.options.get(spec.get('options'), {})
        return self.get_option(option_map, spec.get('attribute'), set_index=set_index,
                               default=spec.get('default'))

    def resolve_identifier(self, spec, set_index=0):
        """Resolve an `{identifier, type, fallback_identifier}` spec."""
        identifier = self.resolve(spec.get('identifier'), set_index=set_index)
        if identifier:
            return {
                'identifier': identifier,
                'type': self.resolve_option(spec.get('type'), set_index=set_index) or 'other'
            }

        fallback = spec.get('fallback_identifier')
        if fallback:
            identifier = self.resolve(fallback, set_index=set_index)
            if identifier:
                return {
                    'identifier': identifier,
                    'type': 'other'
                }

        return None

    # ------------------------------------------------------------------
    # Export functions
    # ------------------------------------------------------------------

    def render(self):
        response = HttpResponse(json.dumps({
            'dmp': self.get_dmp()
        }, indent=2), content_type='application/json')

        if settings.EXPORT_CONTENT_DISPOSITION == 'attachment':
            response['Content-Disposition'] = f'attachment; filename="{self.project.title}.json"'

        return response

    def get_dmp(self):
        mapping = self.mapping.get('dmp', {})
        dmp = defaultdict(list)

        # dmp/title
        title_spec = mapping.get('title', {})
        if 'attribute' in title_spec:
            dmp['title'] = self.resolve(title_spec)
        else:
            dmp['title'] = title_spec.get('template', 'maDMP for {project.title}') \
                                   .format(project=self.project)

        # dmp/created, dmp/modified
        for key in ('created', 'modified'):
            timestamp = self.resolve(mapping.get(key))
            if timestamp:
                dmp[key] = timestamp.isoformat()

        # dmp/contact
        contact_spec = mapping.get('contact')
        if contact_spec:
            contact = self.get_person(contact_spec)
            if contact:
                dmp['contact'] = contact

        # dmp/contributor
        for spec in mapping.get('contributor', []):
            set_attribute = spec.get('set')
            if set_attribute:
                for element in self.get_set(set_attribute):
                    role = spec.get('role_template', '').format(set=element)
                    self._append_contributor(dmp, spec, set_index=element.set_index, role=role)
            else:
                self._append_contributor(dmp, spec, role=spec.get('role_template'))

        # dmp/cost
        for spec in mapping.get('cost', []):
            cost = self.get_cost(spec)
            if cost:
                dmp['cost'].append(cost)

        # dmp/dataset
        dataset_set = self.mapping.get('dataset', {}).get('set', 'project/dataset/id')
        for dataset in self.get_set(dataset_set):
            dmp_dataset = self.get_dataset(dataset)
            if dmp_dataset:
                dmp['dataset'].append(dmp_dataset)

        # dmp/dmp_id
        dmp_id = self.resolve_identifier(mapping.get('dmp_id'))
        if dmp_id:
            dmp['dmp_id'] = dmp_id

        # dmp/dataset/ethical_issues_description

        # dmp/language
        language = self.resolve_option(mapping.get('language'))
        if language:
            dmp['language'] = language

        # dmp/project
        project_spec = mapping.get('project', {})
        project_start = self.resolve(project_spec.get('start'))
        project_end = self.resolve(project_spec.get('end'))
        if project_start and project_end:
            dmp['project'] = [
                {
                    'title': self.resolve(project_spec.get('title')) or self.project.title,
                    'description': self.resolve(project_spec.get('description')),
                    'start': project_start,
                    'end': project_end
                }
            ]

        return dmp

    def _append_contributor(self, dmp, spec, set_index=0, role=None):
        contributor = self.get_person(spec, set_index=set_index, roles=[role] if role else None)
        if contributor:
            dmp['contributor'].append(contributor)

    def get_person(self, spec, set_index=0, roles=None):
        base_attribute = spec.get('base_attribute')
        name_suffix = spec.get('name_suffix', 'name')
        mbox_suffix = spec.get('mbox_suffix', 'mbox')
        identifier_suffix = spec.get('identifier_suffix', 'identifier')

        name = self.get_text(f'{base_attribute}/{name_suffix}', set_index=set_index)
        if name:
            contributor = {
                'name': name
            }

            mbox = self.get_text(f'{base_attribute}/{mbox_suffix}', set_index=set_index)
            if mbox:
                contributor['mbox'] = mbox

            identifier = self.get_text(f'{base_attribute}/{identifier_suffix}', set_index=set_index)
            if identifier:
                contributor['contributor_id'] = {
                    'identifier': identifier,
                    'type': self.get_option(self.options.get('person_id_type_options', {}),
                                            f'{base_attribute}/{identifier_suffix}_type',
                                            set_index=set_index, default='other')
                }

            if roles:
                contributor['role'] = roles

            return contributor
        else:
            return None

    def get_cost(self, spec):
        value = self.get_value(spec.get('attribute'))
        if value is None or not value.text:
            return None

        title = spec.get('title')
        cost = {
            'title': title
        }

        try:
            cost['value'] = int(value.text)
        except ValueError:
            try:
                cost['value'] = float(value.text)
            except ValueError:
                cost['value'] = 0

        if value.unit:
            cost['description'] = f'{title} in {value.unit}'

            # this is a hack to make 'Euro' work
            currency_code = value.unit.upper()[:3]
            if currency_code in self.options.get('currency_codes', []):
                cost['currency_code'] = currency_code

        return cost

    def get_dataset(self, dataset):
        fields = self.mapping.get('dataset', {}).get('fields', {})
        set_index = dataset.set_index
        dmp_dataset = defaultdict(list)

        # dmp/dataset/data_quality_assurance
        data_quality_assurance = self.resolve(fields.get('data_quality_assurance'), set_index)
        if data_quality_assurance:
            dmp_dataset['data_quality_assurance'] = data_quality_assurance

        # dmp/dataset/description
        description = self.resolve(fields.get('description'), set_index)
        if description:
            dmp_dataset['description'] = description

        # dmp/dataset/dataset_id
        dataset_id = self.resolve_identifier(fields.get('dataset_id'), set_index)
        if dataset_id:
            dmp_dataset['dataset_id'] = dataset_id

        # dmp/dataset/distribution (during the project)
        distribution = fields.get('distribution', {})
        during_spec = distribution.get('during', {})
        distribution_during = {}

        # dmp/dataset/distribution/access_url
        access_url = self.resolve(during_spec.get('access_url'), set_index)
        if access_url:
            distribution_during['access_url'] = access_url

        # dmp/dataset/distribution/data_access
        data_access = self.resolve_option(during_spec.get('data_access'), set_index)
        if data_access:
            distribution_during['data_access'] = data_access

        # dmp/dataset/distribution/format
        dmp_format = self.resolve(during_spec.get('format'), set_index)
        if dmp_format:
            distribution_during['format'] = dmp_format

        if distribution_during:
            dmp_dataset['distribution'].append({
                'title': during_spec.get('title', 'Storage during the project'),
                **distribution_during
            })

        # dmp/dataset/distribution (after the project)
        after_spec = distribution.get('after', {})
        distribution_after = {}

        # dmp/dataset/distribution/data_access (derived)
        distribution_after['data_access'] = \
            'open' if distribution_during.get('data_access') == 'open' else 'closed'

        # dmp/dataset/distribution/certified_with
        certified_with = self.resolve_option(after_spec.get('certified_with'), set_index)
        if certified_with:
            distribution_after['certified_with'] = certified_with

        # dmp/dataset/distribution/pid_system
        pid_system = self.resolve_option(after_spec.get('pid_system'), set_index)
        if pid_system:
            distribution_after['pid_system'] = pid_system

        # dmp/dataset/distribution/host
        host_title = self.resolve(after_spec.get('host'), set_index)
        if host_title:
            distribution_after['host'] = {
                'title': host_title
            }

        # dmp/dataset/distribution/license
        license_ref = self.resolve_option(after_spec.get('license_ref'), set_index)
        if license_ref:
            license = {
                'license_ref': license_ref
            }

            start_date = self.resolve(after_spec.get('license_start_date'), set_index)
            if start_date:
                license['start_date'] = start_date

            distribution_after['license'] = [license]

        if distribution_after:
            dmp_dataset['distribution'].append({
                'title': after_spec.get('title', 'Preservation after the project'),
                **distribution_after
            })

        # dmp/dataset/issued
        issued = self.resolve(fields.get('issued'), set_index)
        if issued:
            dmp_dataset['issued'] = issued

        # dmp/dataset/keyword (project-level)
        keywords = self.resolve(fields.get('keyword'))
        if keywords:
            dmp_dataset['keyword'] = keywords

        # dmp/dataset/language
        language = self.resolve_option(fields.get('language'), set_index)
        if language:
            dmp_dataset['language'] = language

        # dmp/dataset/personal_data
        personal_data = self.resolve(fields.get('personal_data'), set_index)
        dmp_dataset['personal_data'] = self.yes_no_unknown[personal_data]

        # dmp/dataset/preservation_statement
        preservation_statement = self.resolve(fields.get('preservation_statement'), set_index)
        if preservation_statement:
            dmp_dataset['preservation_statement'] = preservation_statement

        # dmp/dataset/security_and_privacy
        for spec in fields.get('security_and_privacy', []):
            value = self.get_value(spec.get('attribute'), set_index=set_index)
            if value:
                dmp_dataset['security_and_privacy'].append({
                    'title': spec.get('title'),
                    'description': value.text
                })

        # dmp/dataset/sensitive_data
        sensitive_data = self.resolve(fields.get('sensitive_data'), set_index)
        dmp_dataset['sensitive_data'] = self.yes_no_unknown[sensitive_data]

        # dmp/dataset/type
        dmp_type = self.resolve(fields.get('type'), set_index)
        if dmp_type:
            dmp_dataset['type'] = dmp_type

        # dmp/dataset/title
        dmp_dataset['title'] = self.resolve(fields.get('title_fallback'), set_index) or \
                               f'Dataset #{set_index + 1}'

        return dmp_dataset
