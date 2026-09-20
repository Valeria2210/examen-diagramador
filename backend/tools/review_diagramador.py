"""Reproduce hallazgos de revision en SQLite en memoria, sin tocar diagramas reales.

Ejecutar desde backend: ./.venv/Scripts/python.exe tools/review_diagramador.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
os.environ['DB_ENGINE'] = 'sqlite'
os.environ['DEBUG'] = 'true'

import django
from django.conf import settings

settings.DATABASES = {'default': {
    'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:',
}}
settings.ALLOWED_HOSTS = ['testserver']
django.setup()

from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework.test import APIClient
from diagrams.models import Project, Diagram, Attribute, UMLClass, ProjectMember
from diagrams.xmi_export import diagram_to_xmi
from diagrams.xmi_import import parse_xmi_to_spec

call_command('migrate', verbosity=0)
owner = User.objects.create_user(username='review-owner')
member = User.objects.create_user(username='review-member')
project = Project.objects.create(name='Revision aislada', owner=owner)
diagram = Diagram.objects.create(name='Revision', project=project)
owner_client = APIClient()
owner_client.force_authenticate(owner)
member_client = APIClient()
member_client.force_authenticate(member)

share = owner_client.post(f'/api/projects/{project.pk}/share/', {'role': 'ADMIN'}, format='json')
assert share.status_code == 201, share.data
token = share.data['token']
accepted = member_client.post(f'/api/shares/{token}/accept/')
assert accepted.status_code == 200, accepted.data
demotion = owner_client.post(f'/api/projects/{project.pk}/members/', {
    'username': member.username, 'role': 'VIEWER',
}, format='json')
assert demotion.status_code == 200, demotion.data
before = ProjectMember.objects.get(project=project, user=member).role
reaccepted = member_client.post(f'/api/shares/{token}/accept/')
assert reaccepted.status_code == 200, reaccepted.data
after = ProjectMember.objects.get(project=project, user=member).role

revocation = owner_client.post(f'/api/projects/{project.pk}/revoke_share/', {'token': token}, format='json')
assert revocation.status_code == 204, revocation.data
still_accessible = member_client.get(f'/api/diagrams/{diagram.pk}/full/')
can_still_edit = member_client.post('/api/classes/', {'diagram': diagram.pk, 'name': 'TrasRevocar'}, format='json')

uml_class = UMLClass.objects.create(diagram=diagram, name='Cliente')
Attribute.objects.create(uml_class=uml_class, name='codigo', data_type='String',
    es_pk=True, es_unico=True, nullable=False, longitud=20)
spec = parse_xmi_to_spec(diagram_to_xmi(diagram))
exported_attribute = next(c for c in spec['classes'] if c['name'] == 'Cliente')['attributes'][0]
entity_spec = parse_xmi_to_spec(b'<!DOCTYPE root [<!ENTITY label "ClienteDesdeEntidad">]><root><Class name="&label;"/></root>')

print(json.dumps({
    'base_de_datos': 'SQLite en memoria; sin cambios en datos reales',
    'reaceptar_enlace_tras_degradacion': {'antes': before, 'despues': after},
    'revocar_enlace_no_revoca_membresia': {
        'lectura_http': still_accessible.status_code, 'creacion_http': can_still_edit.status_code,
    },
    'atributo_tras_exportar_importar_xmi': exported_attribute,
    'metadatos_ausentes': sorted({'es_pk', 'es_unico', 'nullable', 'longitud'} - set(exported_attribute)),
    'entidad_xml_interna_aceptada': entity_spec['classes'][0]['name'],
}, ensure_ascii=False, indent=2))
