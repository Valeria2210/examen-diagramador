import io
import zipfile
from diagrams.xmi_import import parse_xmi_to_spec

xml = b'''<xmi:XMI xmlns:xmi="http://schema.omg.org/spec/XMI/2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.1"><uml:Model><packagedElement xmi:type="uml:Class" name="Cliente"/><packagedElement xmi:type="uml:Class" name="Pedido"/></uml:Model></xmi:XMI>'''
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w') as z:
    z.writestr('diagram.xml', xml.decode())

spec = parse_xmi_to_spec(buf.getvalue())
print('classes=', len(spec.get('classes', [])))
print('names=', [c.get('name') for c in spec.get('classes', [])])
print('relations=', len(spec.get('relations', [])))
