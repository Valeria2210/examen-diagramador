import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
os.environ['DEBUG'] = 'False'
os.environ.setdefault('DB_ENGINE', 'postgres')
import django
django.setup()
from pathlib import Path
from zipfile import ZipFile
from django.test import override_settings
from generador.demo_step3 import demo_ir, attr
from generador.services.code_generator import CodeGenerator
from generador.services.ir_builder import IRBuilder
from diagrams.models import Diagram
from diagrams.xmi_export import diagram_to_xmi
from diagrams.xmi_import import parse_xmi_to_spec

base = Path(__file__).resolve().parent / 'audit_output'
base.mkdir(exist_ok=True)
with override_settings(GENERADOR_TMP_DIR=base):
    for label, ir in [('normal', demo_ir()), ('nombre_class', demo_ir()), ('nombre_objects', demo_ir())]:
        if label == 'nombre_class':
            ir['entidades'][0]['atributos'].append(attr('class', 'String'))
        if label == 'nombre_objects':
            ir['entidades'].append({'nombre': 'Objects', 'atributos': [attr('id', 'Long', True)]})
        try:
            filename = CodeGenerator(ir).generar()
            with ZipFile(base / filename) as z:
                z.extractall(base / label)
            print(label, 'ACEPTADO', filename)
        except Exception as exc:
            print(label, type(exc).__name__, str(exc))
    for diagram in Diagram.objects.select_related('project').prefetch_related('classes__attributes', 'classes__methods', 'relations'):
        print('DIAGRAMA_LOCAL', diagram.pk, 'clases', diagram.classes.count(), 'relaciones', diagram.relations.count())
        try:
            builder = IRBuilder(diagram, autocorregir=True)
            ir = builder.construir()
            filename = CodeGenerator(ir, correcciones=builder.avisos).generar()
            with ZipFile(base / filename) as z:
                z.extractall(base / ('diagrama_' + str(diagram.pk)))
            print('GENERACION_LOCAL_OK', diagram.pk, filename)
        except Exception as exc:
            print('GENERACION_LOCAL_ERROR', diagram.pk, type(exc).__name__, str(exc))
        persisted = sum(a.es_pk or a.es_unico or not a.nullable or a.longitud is not None for c in diagram.classes.all() for a in c.attributes.all())
        if persisted:
            spec = parse_xmi_to_spec(diagram_to_xmi(diagram))
            print('XMI_CAMPOS_PERSISTENCIA', diagram.pk, persisted, 'salida_atributo', next((a for c in spec['classes'] for a in c.get('attributes', [])), None))
