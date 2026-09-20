import io
import os
import zipfile

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django

django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

xml = b'''<xmi:XMI xmlns:xmi="http://schema.omg.org/spec/XMI/2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.1"><uml:Model><packagedElement xmi:type="uml:Class" name="Cliente"/><packagedElement xmi:type="uml:Class" name="Pedido"/></uml:Model></xmi:XMI>'''

buffer = io.BytesIO()
with zipfile.ZipFile(buffer, 'w') as zf:
    zf.writestr('diagram.xml', xml.decode('utf-8'))

client = Client()
response = client.post(
    '/api/ai/import-xmi/',
    {'file': SimpleUploadedFile('diagram.qea', buffer.getvalue(), content_type='application/octet-stream')},
    format='multipart',
)

print('status=', response.status_code)
print(response.json())
