import io
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock, call, patch
from xml.etree import ElementTree as ET

import numpy as np
from django.test import SimpleTestCase, TestCase

from diagrams.image_import import DetectedBox, _detect_relations, _split_class_text
from diagrams.models import Attribute, Diagram, Method, Project, Relation, UMLClass
from diagrams.xmi_export import XMI_NS, diagram_to_xmi
from diagrams.xmi_import import parse_xmi_to_spec
from tools.import_enterprise_architect import import_model, open_model, put_method


def xmi(contents):
    return (
        '<xmi:XMI xmlns:xmi="http://www.omg.org/XMI" '
        'xmlns:uml="http://www.omg.org/spec/UML/20131001">'
        f"{contents}</xmi:XMI>"
    ).encode()


class XMIParserRegressionTests(SimpleTestCase):
    def test_type_references_do_not_replace_the_type_definition(self):
        spec = parse_xmi_to_spec(xmi('''
            <uml:PrimitiveType xmi:id="string" name="String"/>
            <uml:Class xmi:id="customer" name="Cliente">
                <ownedAttribute name="nombre"><type xmi:idref="string"/></ownedAttribute>
                <ownedOperation name="buscar" isStatic="true">
                    <ownedParameter name="nombre"><type xmi:idref="string"/></ownedParameter>
                    <ownedParameter direction="return"><type xmi:idref="customer"/></ownedParameter>
                </ownedOperation>
            </uml:Class>
        '''))
        customer = spec["classes"][0]
        self.assertEqual(customer["attributes"][0]["type"], "String")
        self.assertEqual(customer["methods"][0]["parameters"], ["nombre: String"])
        self.assertEqual(customer["methods"][0]["returnType"], "Cliente")
        self.assertTrue(customer["methods"][0]["is_static"])

    def test_association_can_reference_class_owned_member_ends(self):
        spec = parse_xmi_to_spec(xmi('''
            <uml:Class xmi:id="customer" name="Cliente">
                <ownedAttribute xmi:id="orders" name="pedidos" type="order" association="a">
                    <lowerValue value="0"/><upperValue value="*"/>
                </ownedAttribute>
            </uml:Class>
            <uml:Class xmi:id="order" name="Pedido">
                <ownedAttribute xmi:id="client" name="cliente" association="a">
                    <type xmi:idref="customer"/>
                </ownedAttribute>
            </uml:Class>
            <uml:Association xmi:id="a" memberEnd="client orders">
                <memberEnd xmi:idref="client"/><memberEnd xmi:idref="orders"/>
            </uml:Association>
        '''))
        self.assertEqual(spec["relations"], [{
            "from": "Cliente", "to": "Pedido", "type": "ASSOCIATION",
            "sourceMultiplicity": "1", "targetMultiplicity": "0..*", "label": "",
        }])

    def test_missing_multiplicity_bound_uses_uml_default(self):
        spec = parse_xmi_to_spec(xmi('''
            <uml:Class xmi:id="a" name="A"/><uml:Class xmi:id="b" name="B"/>
            <uml:Association>
                <ownedEnd type="a"><lowerValue value="0"/></ownedEnd>
                <ownedEnd type="b"><upperValue value="*"/></ownedEnd>
            </uml:Association>
        '''))
        relation = spec["relations"][0]
        self.assertEqual(relation["sourceMultiplicity"], "0..1")
        self.assertEqual(relation["targetMultiplicity"], "1..*")

    def test_archive_skips_invalid_xml_candidates(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("invalid.xml", "not XML")
            archive.writestr("model.xmi", xmi('<uml:Class name="Cliente"/>'))
        self.assertEqual(parse_xmi_to_spec(buffer.getvalue())["classes"][0]["name"], "Cliente")

    def test_archive_rejects_oversized_decompressed_xml(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("model.xml", b" " * (16 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(ET.ParseError, "16 MiB"):
            parse_xmi_to_spec(buffer.getvalue())

    def test_plain_xml_rejects_oversized_payload(self):
        with self.assertRaisesRegex(ET.ParseError, "16 MiB"):
            parse_xmi_to_spec(b" " * (16 * 1024 * 1024 + 1))

    def test_enterprise_architect_xmi_1_style_members_and_generalization(self):
        payload = b'''<XMI xmlns:UML="org.omg.xmi.namespace.UML" xmlns:xmi="http://www.omg.org/XMI">
          <UML:Model xmi.id="model" name="EA">
            <UML:Class xmi.id="base" name="Persona"/>
            <UML:Class xmi.id="child" name="Cliente">
              <UML:Classifier.feature>
                <UML:Attribute xmi.id="a1" name="nombre" visibility="private">
                  <UML:StructuralFeature.type><UML:Classifier xmi.idref="string"/></UML:StructuralFeature.type>
                </UML:Attribute>
                <UML:Operation xmi.id="op1" name="buscar">
                  <UML:BehavioralFeature.parameter>
                    <UML:Parameter name="id"><UML:Parameter.type><UML:Classifier xmi.idref="integer"/></UML:Parameter.type></UML:Parameter>
                  </UML:BehavioralFeature.parameter>
                </UML:Operation>
              </UML:Classifier.feature>
            </UML:Class>
            <UML:DataType xmi.id="string" name="String"/><UML:DataType xmi.id="integer" name="Integer"/>
            <UML:Generalization xmi.id="g1" subtype="child" supertype="base"/>
          </UML:Model>
        </XMI>'''
        spec = parse_xmi_to_spec(payload)
        customer = next(item for item in spec["classes"] if item["name"] == "Cliente")
        self.assertEqual(customer["attributes"][0]["type"], "String")
        self.assertEqual(customer["methods"][0]["parameters"], ["id: Integer"])
        self.assertEqual(spec["relations"][0]["from"], "Cliente")
        self.assertEqual(spec["relations"][0]["to"], "Persona")


class XMIExportRegressionTests(TestCase):
    def test_export_preserves_class_types_static_members_and_relations(self):
        diagram = Diagram.objects.create(project=Project.objects.create(name="Tipos"), name="Tipos")
        order = UMLClass.objects.create(diagram=diagram, name="Pedido")
        customer = UMLClass.objects.create(diagram=diagram, name="Cliente")
        Attribute.objects.create(uml_class=order, name="cliente", data_type="Cliente", is_static=True)
        Method.objects.create(
            uml_class=order, name="buscar", return_type="Cliente", is_static=True,
            parameters=[{"name": "cliente", "type": "Cliente"}],
        )
        Relation.objects.create(
            diagram=diagram, source=order, target=customer, relation_type="ASSOCIATION",
            multiplicity_source="0..*", multiplicity_target="1",
        )
        payload = diagram_to_xmi(diagram)
        xml = ET.fromstring(payload)
        customer_el = next(el for el in xml.iter() if el.get("name") == "Cliente")
        attr = next(el for el in xml.iter() if el.tag == "ownedAttribute")
        self.assertEqual(attr.find("type").get(f"{{{XMI_NS}}}idref"), customer_el.get(f"{{{XMI_NS}}}id"))
        self.assertEqual(len([el for el in xml.iter() if el.get("name") == "Cliente"]), 1)
        spec = parse_xmi_to_spec(payload)
        imported_order = next(item for item in spec["classes"] if item["name"] == "Pedido")
        self.assertEqual(imported_order["attributes"][0]["type"], "Cliente")
        self.assertTrue(imported_order["attributes"][0]["is_static"])
        self.assertEqual(imported_order["methods"][0]["parameters"], ["cliente: Cliente"])
        self.assertTrue(imported_order["methods"][0]["is_static"])
        self.assertEqual(spec["relations"][0]["sourceMultiplicity"], "0..*")


class ImageImportRegressionTests(SimpleTestCase):
    def test_ocr_parameters_use_the_frontend_string_contract(self):
        parsed = _split_class_text("Cliente\n+buscar(nombre: String, Integer edad, activo): Boolean")
        self.assertEqual(parsed["methods"][0]["parameters"], ["nombre: String", "edad: Integer", "activo: String"])

    def test_inheritance_direction_follows_the_arrow_not_box_order(self):
        image = np.full((200, 500), 255, dtype=np.uint8)
        boxes = [DetectedBox(0, 50, 100, 100, "Base"), DetectedBox(300, 50, 100, 100, "Derivada")]
        with (
            patch("diagrams.image_import._nearby_line_segments", return_value=[(100, 100, 300, 100)]),
            patch("diagrams.image_import._has_diamond", return_value=False),
            patch("diagrams.image_import._has_arrowhead", side_effect=lambda _, point: point == (100, 100)),
            patch("diagrams.image_import._read_multiplicity", return_value="1"),
        ):
            relations = _detect_relations(image, boxes)
        self.assertEqual(relations[0]["type"], "INHERITANCE")
        self.assertEqual((relations[0]["from"], relations[0]["to"]), ("Derivada", "Base"))

    def test_aggregation_direction_and_multiplicity_follow_the_diamond(self):
        image = np.full((200, 500), 255, dtype=np.uint8)
        boxes = [DetectedBox(0, 50, 100, 100, "Todo"), DetectedBox(300, 50, 100, 100, "Parte")]
        with (
            patch("diagrams.image_import._nearby_line_segments", return_value=[(100, 100, 300, 100)]),
            patch("diagrams.image_import._has_diamond", side_effect=lambda _, point: point == (100, 100)),
            patch("diagrams.image_import._read_multiplicity", side_effect=lambda _, point: "1" if point == (100, 100) else "0..*"),
        ):
            relations = _detect_relations(image, boxes)
        self.assertEqual(relations[0]["type"], "AGGREGATION")
        self.assertEqual((relations[0]["from"], relations[0]["to"]), ("Parte", "Todo"))
        self.assertEqual(relations[0]["sourceMultiplicity"], "0..*")
        self.assertEqual(relations[0]["targetMultiplicity"], "1")


class EnterpriseArchitectRegressionTests(SimpleTestCase):
    def test_open_model_uses_the_documented_create_signature(self):
        repository = Mock()
        with patch("tools.import_enterprise_architect.os.path.exists", return_value=False):
            open_model(repository, "model.qeax")
        repository.CreateModel.assert_called_once_with(0, "model.qeax", 0)
        repository.OpenFile.assert_called_once_with("model.qeax")

    def test_open_model_does_not_continue_after_creation_failure(self):
        repository = Mock()
        repository.CreateModel.return_value = False
        with patch("tools.import_enterprise_architect.os.path.exists", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "crear"):
                open_model(repository, "model.qeax")
        repository.OpenFile.assert_not_called()

    def test_exported_json_relations_resolve_database_class_ids(self):
        repository = SimpleNamespace(Models=Mock())
        package = repository.Models.AddNew.return_value
        source = Mock(ElementID=100)
        target = Mock(ElementID=200)
        package.Elements.AddNew.side_effect = [source, target]
        import_model(repository, {
            "classes": [{"id": 1, "name": "Cliente"}, {"id": 2, "name": "Pedido"}],
            "relations": [{"source": 1, "target": 2, "relation_type": "INHERITANCE"}],
        })
        source.Connectors.AddNew.assert_called_once_with("", "Generalization")
        self.assertEqual(source.Connectors.AddNew.return_value.SupplierID, 200)
        diagram = package.Diagrams.AddNew.return_value
        package.Diagrams.AddNew.assert_called_once_with("Diagrama UML", "Class")
        self.assertEqual(diagram.DiagramObjects.AddNew.call_count, 2)
        first_object = diagram.DiagramObjects.AddNew.return_value
        self.assertEqual(first_object.ElementID, 200)

    def test_json_import_preserves_element_geometry_and_enum_kind(self):
        repository = SimpleNamespace(Models=Mock())
        package = repository.Models.AddNew.return_value
        element = Mock(ElementID=42)
        package.Elements.AddNew.return_value = element
        import_model(repository, {"name": "Ventas", "classes": [{
            "id": 1, "name": "Estado", "kind": "ENUM", "pos_x": 15, "pos_y": 25,
            "width": 180, "height": 100,
        }], "relations": []})
        package.Elements.AddNew.assert_called_once_with("Estado", "Enumeration")
        diagram_object = package.Diagrams.AddNew.return_value.DiagramObjects
        diagram_object.AddNew.assert_called_once_with("l=15;r=195;t=-25;b=-125;", "")
        self.assertEqual(diagram_object.AddNew.return_value.ElementID, 42)

    def test_method_is_persisted_before_adding_parameters(self):
        ea_class = Mock()
        put_method(ea_class, {"name": "buscar", "parameters": [{"name": "id", "type": "Integer"}]})
        item = ea_class.Methods.AddNew.return_value
        self.assertLess(item.mock_calls.index(call.Update()), item.mock_calls.index(call.Parameters.AddNew("id", "Integer")))
