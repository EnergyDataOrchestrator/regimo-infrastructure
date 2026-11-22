"""One-off test: import a modified fixture XML into a scratch RDMO project.

Replicates ProjectImportMixin.import_file (project-create path): process() the
XML, save the parsed project, then save_import_values with all value keys
"checked" (as the confirm form does by default). Prints the imported dataset
values and deletes the scratch project afterwards, leaving the DB unchanged.
"""
import sys
import types

rdmo_app = sys.argv[1]
xml_file = sys.argv[2]

sys.path.insert(0, rdmo_app)
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from rdmo.projects.imports import RDMOXMLImport
from rdmo.projects.models import Membership, Project, Value
from rdmo.projects.utils import save_import_values

user = get_user_model().objects.get(username="admin")
request = types.SimpleNamespace(user=user)

import_plugin = RDMOXMLImport("xml", "RDMO XML", "rdmo.projects.imports.RDMOXMLImport")
import_plugin.file_name = xml_file
import_plugin.request = request
import_plugin.current_project = None

assert import_plugin.check(), "check() failed — not a readable project XML"
import_plugin.process()

# -- save like the import view does ---------------------------------------
project = import_plugin.project
project.site = Site.objects.first()
project.save()
Membership.objects.create(project=project, user=user, role="owner")
for value in import_plugin.values:
    value.current = None
checked = [f"{v.attribute.uri}[{v.set_prefix}][{v.set_index}][{v.collection_index}]"
           for v in import_plugin.values if v.attribute]
save_import_values(project, import_plugin.values, checked)

project = Project.objects.get(pk=project.pk)
print("imported project:", project.pk, repr(project.title))
ds = Value.objects.filter(project=project, attribute__path="project/dataset/id")
for v in ds:
    print("  dataset set value:", v.set_index, repr(v.text))
for path in ("project/dataset/description", "project/dataset/format",
             "project/dataset/creation_methods"):
    for v in Value.objects.filter(project=project, attribute__path=path):
        print(f"  {path} (set {v.set_index}):", repr(v.text)[:140])
print("total values:", Value.objects.filter(project=project).count())

project.delete()
print("scratch project deleted; Project count back to",
      Project.objects.count())
