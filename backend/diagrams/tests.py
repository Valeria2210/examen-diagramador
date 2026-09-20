import io
import json
import zipfile
from unittest.mock import patch

import cv2
import numpy as np
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from diagrams.models import Diagram, Project, ProjectMember, ProjectShare, UMLClass, Relation
from diagrams.image_import import DetectedBox, _detect_relations
from diagrams.uml_analysis import analyze_diagram
from diagrams.xmi_export import diagram_to_xmi
from diagrams.xmi_import import parse_xmi_to_spec


class XMIImportTests(TestCase):
    def test_export_xmi_uses_ea_compatible_namespaces_and_diagram_name(self):
        project = Project.objects.create(name="EA project")
        diagram = Diagram.objects.create(project=project, name="Ventas UML")

        xml = diagram_to_xmi(diagram)

        self.assertIn(b'xmlns:xmi="http://www.omg.org/spec/XMI/20131001"', xml)
        self.assertIn(b'xmlns:uml="http://www.omg.org/spec/UML/20131001"', xml)
        self.assertIn(b'name="Ventas UML"', xml)
        self.assertIn(b'exporter="Diagramador UML"', xml)

    def test_parse_xmi_from_qea_archive(self):
        xml = b'''<xmi:XMI xmlns:xmi="http://schema.omg.org/spec/XMI/2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.1">
            <uml:Model>
                <packagedElement xmi:type="uml:Class" name="Cliente">
                    <ownedAttribute xmi:type="uml:Property" name="nombre" visibility="private"/>
                </packagedElement>
                <packagedElement xmi:type="uml:Class" name="Pedido"/>
            </uml:Model>
        </xmi:XMI>'''

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("model.xml", xml.decode("utf-8"))

        spec = parse_xmi_to_spec(buffer.getvalue())

        self.assertEqual(len(spec["classes"]), 2)
        self.assertEqual({c["name"] for c in spec["classes"]}, {"Cliente", "Pedido"})

    def test_parse_classes_and_association_by_xml_ids(self):
        xml = b'''<xmi:XMI xmlns:xmi="http://www.omg.org/XMI" xmlns:uml="http://www.omg.org/spec/UML/20131001">
            <uml:Model xmi:id="model">
                <packagedElement xmi:type="uml:Class" xmi:id="class_1" name="Cliente">
                    <ownedAttribute xmi:id="attr_1" name="nombre" visibility="private"><type xmi:idref="string_1"/></ownedAttribute>
                </packagedElement>
                <packagedElement xmi:type="uml:Class" xmi:id="class_2" name="Pedido"/>
                <packagedElement xmi:type="uml:PrimitiveType" xmi:id="string_1" name="String"/>
                <packagedElement xmi:type="uml:Association" xmi:id="association_1">
                    <ownedEnd xmi:id="end_1" type="class_1"><lowerValue value="1"/><upperValue value="1"/></ownedEnd>
                    <ownedEnd xmi:id="end_2" type="class_2" aggregation="composite"><lowerValue value="0"/><upperValue value="*"/></ownedEnd>
                </packagedElement>
            </uml:Model>
        </xmi:XMI>'''
        spec = parse_xmi_to_spec(xml)
        self.assertEqual({c["name"] for c in spec["classes"]}, {"Cliente", "Pedido"})
        self.assertEqual(spec["classes"][0]["attributes"][0]["type"], "String")
        self.assertEqual(spec["relations"], [{
            "from": "Cliente", "to": "Pedido", "type": "COMPOSITION",
            "sourceMultiplicity": "1", "targetMultiplicity": "0..*", "label": "",
        }])

    def test_import_xmi_creates_database_objects(self):
        user = User.objects.create_user(username="xmi-user", password="password123")
        project = Project.objects.create(name="XMI project", owner=user)
        diagram = Diagram.objects.create(project=project, name="XMI diagram")
        xml = b'''<xmi:XMI xmlns:xmi="http://schema.omg.org/spec/XMI/2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.1">
            <uml:Model><packagedElement xmi:type="uml:Class" xmi:id="a" name="Cliente"/><packagedElement xmi:type="uml:Class" xmi:id="b" name="Pedido"/>
            </uml:Model></xmi:XMI>'''
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/diagrams/{diagram.id}/import_xmi/",
            {"file": SimpleUploadedFile("model.xmi", xml, content_type="application/xml")},
            format="multipart",
            SERVER_NAME="127.0.0.1",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(diagram.classes.count(), 2)


class UMLInterpretationTests(TestCase):
    def test_interpret_uml_uses_claude_tool_call(self):
        user = User.objects.create_user(username="tool-user", password="password123")
        project = Project.objects.create(name="Tool project", owner=user)
        diagram = Diagram.objects.create(project=project, name="Tool diagram")
        response_payload = {
            "content": [{
                "type": "tool_use",
                "name": "create_uml_diagram",
                "input": {
                    "classes": [{"name": "Cliente", "kind": "CLASS", "attributes": [], "methods": []}],
                    "relations": [],
                },
            }],
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(response_payload).encode("utf-8")

        client = APIClient()
        client.force_authenticate(user=user)
        with patch("diagrams.views.config", side_effect=lambda key, default="": "test-key" if key == "ANTHROPIC_API_KEY" else default), patch("diagrams.views.urllib_request.urlopen", return_value=FakeResponse()) as urlopen:
            response = client.post(f"/api/ai/interpret-uml/", {"description": "Crea una clase Cliente"}, format="json", SERVER_NAME="127.0.0.1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["classes"][0]["name"], "Cliente")
        sent_payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(sent_payload["tool_choice"], {"type": "tool", "name": "create_uml_diagram"})
        self.assertEqual(sent_payload["tools"][0]["name"], "create_uml_diagram")


class UMLAnalysisTests(TestCase):
    def test_analyze_diagram_reports_duplicates_and_missing_multiplicity(self):
        project = Project.objects.create(name="Analysis project")
        diagram = Diagram.objects.create(project=project, name="Analysis diagram")
        first = UMLClass.objects.create(diagram=diagram, name="Cliente")
        second = UMLClass.objects.create(diagram=diagram, name="cliente")
        Relation.objects.create(
            diagram=diagram,
            source=first,
            target=second,
            relation_type="ASSOCIATION",
            multiplicity_source="",
            multiplicity_target="1",
        )

        result = analyze_diagram(diagram)

        self.assertEqual(result["summary"]["errors"], 1)
        self.assertEqual(result["summary"]["warnings"], 2)
        self.assertEqual(
            {finding["code"] for finding in result["findings"]},
            {"DUPLICATE_CLASS", "MISSING_MULTIPLICITY", "INCONSISTENT_CLASS_NAME"},
        )

    def test_analyze_endpoint_is_scoped_to_authenticated_owner(self):
        user = User.objects.create_user(username="analysis-user", password="password123")
        project = Project.objects.create(name="Owned project", owner=user)
        diagram = Diagram.objects.create(project=project, name="Owned diagram")
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get(f"/api/diagrams/{diagram.id}/analyze/", SERVER_NAME="127.0.0.1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["diagram_id"], diagram.id)


class ImageRecognitionTests(TestCase):
    def test_detect_relations_from_boxes_without_ocr(self):
        image = np.full((240, 520), 255, dtype=np.uint8)
        cv2.rectangle(image, (20, 80), (160, 180), 0, 3)
        cv2.rectangle(image, (360, 80), (500, 180), 0, 3)
        cv2.line(image, (160, 130), (360, 130), 0, 3)

        relations = _detect_relations(image, [
            DetectedBox(20, 80, 140, 100, "Cliente"),
            DetectedBox(360, 80, 140, 100, "Pedido"),
        ])

        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["type"], "ASSOCIATION")
        self.assertEqual(relations[0]["sourceMultiplicity"], "1")


class ProjectSharingTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="password123")
        self.viewer = User.objects.create_user(username="viewer", password="password123")
        self.editor = User.objects.create_user(username="editor", password="password123")
        self.project = Project.objects.create(name="Sistema de Ventas", owner=self.owner)
        self.diagram = Diagram.objects.create(project=self.project, name="Diagrama principal")

    def test_owner_creates_and_revokes_share_link(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)

        response = client.post(f"/api/projects/{self.project.id}/share/", {"role": "VIEWER"}, format="json")

        self.assertEqual(response.status_code, 201)
        token = response.json()["token"]
        self.assertTrue(ProjectShare.objects.filter(token=token, active=True).exists())
        revoke = client.post(f"/api/projects/{self.project.id}/revoke_share/", {"token": token}, format="json")
        self.assertEqual(revoke.status_code, 204)
        self.assertFalse(ProjectShare.objects.get(token=token).active)

    def test_viewer_can_accept_link_but_cannot_edit(self):
        share = ProjectShare.objects.create(project=self.project, created_by=self.owner, role="VIEWER")
        existing_class = UMLClass.objects.create(diagram=self.diagram, name="Cliente")
        client = APIClient()
        client.force_authenticate(user=self.viewer)

        accepted = client.post(f"/api/shares/{share.token}/accept/", {}, format="json")
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(ProjectMember.objects.get(project=self.project, user=self.viewer).role, "VIEWER")
        diagrams = client.get("/api/diagrams/")
        self.assertEqual(diagrams.status_code, 200)
        denied = client.post("/api/classes/", {"diagram": self.diagram.id, "name": "Pedido", "kind": "CLASS"}, format="json")
        self.assertEqual(denied.status_code, 403)
        denied_update = client.patch(f"/api/classes/{existing_class.id}/", {"name": "Cliente editado"}, format="json")
        self.assertEqual(denied_update.status_code, 403)

    def test_editor_can_edit_shared_project(self):
        share = ProjectShare.objects.create(project=self.project, created_by=self.owner, role="EDITOR")
        client = APIClient()
        client.force_authenticate(user=self.editor)
        self.assertEqual(client.post(f"/api/shares/{share.token}/accept/", {}, format="json").status_code, 200)

        response = client.post("/api/classes/", {"diagram": self.diagram.id, "name": "Cliente", "kind": "CLASS"}, format="json")

        self.assertEqual(response.status_code, 201)


class DiagramVersionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="version-user", password="password123")
        self.project = Project.objects.create(name="Version project", owner=self.user)
        self.diagram = Diagram.objects.create(project=self.project, name="Version diagram")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_version_can_be_created_listed_and_restored(self):
        created = self.client.post(f"/api/diagrams/{self.diagram.id}/versions/", {"label": "Base"}, format="json")
        self.assertEqual(created.status_code, 201)
        version_id = created.json()["id"]
        UMLClass.objects.create(diagram=self.diagram, name="Actual")

        restored = self.client.post(f"/api/diagrams/{self.diagram.id}/restore_version/", {"version_id": version_id}, format="json")

        self.assertEqual(restored.status_code, 200)
        self.assertFalse(self.diagram.classes.filter(name="Actual").exists())
        self.assertGreaterEqual(self.diagram.versions.count(), 3)
