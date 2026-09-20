from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Attribute, Diagram, DiagramVersion, Method, Project, ProjectMember, ProjectShare, Relation, UMLClass
from .views import create_diagram_version, diagram_snapshot
from .xmi_export import diagram_to_xmi


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1"])
class SharingPermissionRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="sharing-owner")
        cls.sharer = User.objects.create_user(username="sharing-sharer")
        cls.editor = User.objects.create_user(username="sharing-editor")
        cls.recipient = User.objects.create_user(username="sharing-recipient")
        cls.project = Project.objects.create(name="Compartido", owner=cls.owner)
        ProjectMember.objects.create(project=cls.project, user=cls.sharer, role="SHARER")
        ProjectMember.objects.create(project=cls.project, user=cls.editor, role="EDITOR")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.sharer)

    def test_sharer_cannot_grant_edit_or_admin_or_accept_legacy_self_escalation_links(self):
        for role in ("EDITOR", "ADMIN"):
            with self.subTest(role=role):
                response = self.client.post(
                    f"/api/projects/{self.project.pk}/share/", {"role": role}, format="json"
                )
                self.assertEqual(response.status_code, 403, response.data)
                self.assertFalse(ProjectShare.objects.filter(role=role).exists())
                legacy = ProjectShare.objects.create(project=self.project, created_by=self.sharer, role=role)
                accepted = self.client.post(f"/api/shares/{legacy.token}/accept/", {}, format="json")
                self.assertEqual(accepted.status_code, 403, accepted.data)
                self.assertEqual(ProjectMember.objects.get(project=self.project, user=self.sharer).role, "SHARER")

    def test_sharer_can_issue_viewer_and_sharer_links(self):
        for role in ("VIEWER", "SHARER"):
            with self.subTest(role=role):
                response = self.client.post(
                    f"/api/projects/{self.project.pk}/share/", {"role": role}, format="json"
                )
                self.assertEqual(response.status_code, 201, response.data)
                self.assertTrue(ProjectShare.objects.filter(
                    token=response.data["token"], role=role, created_by=self.sharer
                ).exists())

    def test_sharer_lists_and_revokes_only_their_own_links(self):
        own_link = ProjectShare.objects.create(project=self.project, created_by=self.sharer, role="VIEWER")
        owner_link = ProjectShare.objects.create(project=self.project, created_by=self.owner, role="ADMIN")
        listed = self.client.get(f"/api/projects/{self.project.pk}/shares/")
        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual([item["token"] for item in listed.data], [str(own_link.token)])
        denied = self.client.post(
            f"/api/projects/{self.project.pk}/revoke_share/", {"token": str(owner_link.token)}, format="json"
        )
        self.assertEqual(denied.status_code, 404, denied.data)
        owner_link.refresh_from_db()
        self.assertTrue(owner_link.active)
        revoked = self.client.post(
            f"/api/projects/{self.project.pk}/revoke_share/", {"token": str(own_link.token)}, format="json"
        )
        self.assertEqual(revoked.status_code, 204)
        own_link.refresh_from_db()
        self.assertFalse(own_link.active)

    def test_revoking_invalid_uuid_returns_bad_request(self):
        for token in ("not-a-uuid", None, [], {"id": 1}):
            with self.subTest(token=token):
                response = self.client.post(
                    f"/api/projects/{self.project.pk}/revoke_share/", {"token": token}, format="json"
                )
                self.assertEqual(response.status_code, 400, response.data)

    def test_links_cannot_outlive_the_issuers_permission_to_grant_them(self):
        membership = ProjectMember.objects.get(project=self.project, user=self.sharer)
        self.client.force_authenticate(user=self.recipient)
        for shared_role, current_role in (("ADMIN", "SHARER"), ("EDITOR", "SHARER"), ("VIEWER", "VIEWER")):
            with self.subTest(shared_role=shared_role, current_role=current_role):
                link = ProjectShare.objects.create(project=self.project, created_by=self.sharer, role=shared_role)
                membership.role = current_role
                membership.save(update_fields=["role"])
                response = self.client.post(f"/api/shares/{link.token}/accept/", {}, format="json")
                self.assertEqual(response.status_code, 403, response.data)
                self.assertFalse(ProjectMember.objects.filter(project=self.project, user=self.recipient).exists())

    def test_editor_accepting_sharer_link_retains_editing_and_reports_effective_role(self):
        link = ProjectShare.objects.create(project=self.project, created_by=self.sharer, role="SHARER")
        self.client.force_authenticate(user=self.editor)
        response = self.client.post(f"/api/shares/{link.token}/accept/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["role"], "EDITOR")
        self.assertEqual(ProjectMember.objects.get(project=self.project, user=self.editor).role, "EDITOR")
        created = self.client.post(
            "/api/diagrams/", {"project": self.project.pk, "name": "Edición conservada"}, format="json"
        )
        self.assertEqual(created.status_code, 201, created.data)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1"])
class DiagramHistoryRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="history-owner")
        cls.project = Project.objects.create(name="Historial", owner=cls.owner)
        cls.diagram = Diagram.objects.create(project=cls.project, name="Versión original")
        cls.source = UMLClass.objects.create(
            diagram=cls.diagram, name="Cliente", pos_x=-75, pos_y=250, width=412.5, height=298
        )
        cls.target = UMLClass.objects.create(diagram=cls.diagram, name="Pedido")
        cls.attribute = Attribute.objects.create(
            uml_class=cls.source, name="contador", data_type="Long", is_static=True
        )
        cls.method = Method.objects.create(
            uml_class=cls.source, name="buscar", return_type="Cliente", is_static=True,
            parameters=[{"name": "id", "type": "Long"}, {"name": "activo", "type": "Boolean"}],
        )
        cls.relation = Relation.objects.create(
            diagram=cls.diagram, source=cls.source, target=cls.target, label="realiza",
            multiplicity_source="1", multiplicity_target="0..*",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_crud_rolls_back_data_and_history_when_snapshot_write_fails(self):
        before = diagram_snapshot(self.diagram)
        operations = [
            ("post", "/api/diagrams/", {"project": self.project.pk, "name": "Fallido"}),
            ("post", "/api/classes/", {"diagram": self.diagram.pk, "name": "Fallida"}),
            ("patch", f"/api/classes/{self.source.pk}/", {"name": "Cambio fallido"}),
            ("delete", f"/api/classes/{self.source.pk}/", None),
        ]
        for method, url, payload in operations:
            with self.subTest(method=method, url=url):
                def failing_version(*args, **kwargs):
                    if method == "delete" and args[2] == "Antes de eliminar":
                        return create_diagram_version(*args, **kwargs)
                    raise RuntimeError("snapshot failed")

                with patch("diagrams.views.create_diagram_version", side_effect=failing_version):
                    with self.assertRaisesMessage(RuntimeError, "snapshot failed"):
                        getattr(self.client, method)(url, payload, format="json")
                self.diagram.refresh_from_db()
                self.assertEqual(diagram_snapshot(self.diagram), before)
                self.assertEqual(Diagram.objects.count(), 1)
                self.assertEqual(DiagramVersion.objects.count(), 0)

    def test_deleting_diagram_returns_204_and_removes_its_children(self):
        create_diagram_version(self.diagram, self.owner, "Manual")
        response = self.client.delete(f"/api/diagrams/{self.diagram.pk}/")
        self.assertEqual(response.status_code, 204)
        for model in (Diagram, DiagramVersion, UMLClass, Attribute, Method, Relation):
            self.assertEqual(model.objects.count(), 0, model.__name__)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())

    def test_restoring_version_preserves_name_dimensions_and_members(self):
        version = create_diagram_version(self.diagram, self.owner, "Original")
        Diagram.objects.filter(pk=self.diagram.pk).update(name="Nombre cambiado")
        UMLClass.objects.filter(pk=self.source.pk).update(width=100, height=100)
        self.method.delete()
        response = self.client.post(
            f"/api/diagrams/{self.diagram.pk}/restore_version/", {"version_id": version.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.diagram.refresh_from_db()
        self.assertEqual(self.diagram.name, "Versión original")
        restored = self.diagram.classes.get(name="Cliente")
        self.assertEqual((restored.pos_x, restored.pos_y, restored.width, restored.height), (-75, 250, 412.5, 298))
        self.assertTrue(restored.attributes.get(name="contador").is_static)
        method = restored.methods.get(name="buscar")
        self.assertTrue(method.is_static)
        self.assertEqual(method.parameters, [{"name": "id", "type": "Long"}, {"name": "activo", "type": "Boolean"}])
        self.assertEqual(self.diagram.relations.get().target.name, "Pedido")
        self.assertEqual(self.diagram.versions.count(), 3)

    def test_restore_rolls_back_deleted_content_when_rebuilding_fails(self):
        version = create_diagram_version(self.diagram, self.owner, "Original")
        before = diagram_snapshot(self.diagram)
        with patch("diagrams.views.Method.objects.create", side_effect=RuntimeError("restore failed")):
            with self.assertRaisesMessage(RuntimeError, "restore failed"):
                self.client.post(
                    f"/api/diagrams/{self.diagram.pk}/restore_version/", {"version_id": version.pk}, format="json"
                )
        self.diagram.refresh_from_db()
        self.assertEqual(diagram_snapshot(self.diagram), before)
        self.assertEqual(self.diagram.versions.count(), 1)

    def test_save_as_preserves_geometry_members_and_relationships(self):
        response = self.client.post(
            f"/api/diagrams/{self.diagram.pk}/save_as/", {"name": "Copia"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        duplicate = Diagram.objects.get(pk=response.data["id"])
        copied = duplicate.classes.get(name="Cliente")
        self.assertNotEqual(copied.pk, self.source.pk)
        self.assertEqual((copied.pos_x, copied.pos_y, copied.width, copied.height), (-75, 250, 412.5, 298))
        self.assertTrue(copied.attributes.get().is_static)
        self.assertEqual(copied.methods.get().parameters, self.method.parameters)
        self.assertTrue(copied.methods.get().is_static)
        relation = duplicate.relations.get()
        self.assertEqual(relation.source_id, copied.pk)
        self.assertEqual(relation.target.diagram_id, duplicate.pk)
        self.assertEqual(relation.multiplicity_target, "0..*")
        self.assertEqual(response.data["access_role"], "OWNER")
        self.assertEqual(duplicate.versions.get().snapshot["name"], "Copia")

    def test_save_as_rolls_back_partial_copy_when_relationship_write_fails(self):
        before = diagram_snapshot(self.diagram)
        with patch("diagrams.views.Relation.objects.create", side_effect=RuntimeError("copy failed")):
            with self.assertRaisesMessage(RuntimeError, "copy failed"):
                self.client.post(f"/api/diagrams/{self.diagram.pk}/save_as/", {"name": "Fallida"}, format="json")
        self.assertEqual(Diagram.objects.count(), 1)
        self.assertEqual(UMLClass.objects.count(), 2)
        self.assertEqual(Attribute.objects.count(), 1)
        self.assertEqual(Method.objects.count(), 1)
        self.assertEqual(DiagramVersion.objects.count(), 0)
        self.diagram.refresh_from_db()
        self.assertEqual(diagram_snapshot(self.diagram), before)

    @override_settings(DIAGRAM_AUTO_VERSION_LIMIT=2)
    def test_automatic_history_is_bounded_and_manual_versions_are_kept(self):
        original = create_diagram_version(self.diagram, self.owner, "Manual original")
        for index in range(4):
            response = self.client.patch(
                f"/api/classes/{self.source.pk}/", {"pos_x": index * 10}, format="json"
            )
            self.assertEqual(response.status_code, 200, response.data)
            if index == 1:
                middle = create_diagram_version(self.diagram, self.owner, "Manual intermedia")
        self.assertEqual(self.diagram.versions.filter(is_automatic=True).count(), 2)
        self.assertEqual(set(self.diagram.versions.filter(is_automatic=False).values_list("pk", flat=True)),
                         {original.pk, middle.pk})
        automatic_numbers = list(self.diagram.versions.filter(is_automatic=True).values_list("version_number", flat=True))
        self.assertEqual(automatic_numbers, [6, 5])
        self.assertEqual(self.diagram.versions.first().snapshot["classes"][0]["pos_x"], 30)

    def test_duplicate_xmi_import_rolls_back_new_classes_and_snapshot(self):
        create_diagram_version(self.diagram, self.owner, "Antes")
        before = diagram_snapshot(self.diagram)
        xml = b'''<xmi:XMI xmlns:xmi="http://www.omg.org/XMI" xmlns:uml="http://www.omg.org/spec/UML/20131001">
            <uml:Model><packagedElement xmi:type="uml:Class" xmi:id="new" name="Nueva"/>
            <packagedElement xmi:type="uml:Class" xmi:id="duplicate" name="cliente"/></uml:Model></xmi:XMI>'''
        response = self.client.post(
            f"/api/diagrams/{self.diagram.pk}/import_xmi/",
            {"file": SimpleUploadedFile("duplicate.xmi", xml, content_type="application/xml")}, format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("name", response.data)
        self.diagram.refresh_from_db()
        self.assertEqual(diagram_snapshot(self.diagram), before)
        self.assertEqual(self.diagram.versions.count(), 1)

    def test_xmi_round_trip_preserves_method_parameters_and_static_members(self):
        target = Diagram.objects.create(project=self.project, name="Importado")
        response = self.client.post(
            f"/api/diagrams/{target.pk}/import_xmi/",
            {"file": SimpleUploadedFile("roundtrip.xmi", diagram_to_xmi(self.diagram), content_type="application/xml")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        imported = target.classes.get(name="Cliente")
        self.assertTrue(imported.attributes.get(name="contador").is_static)
        method = imported.methods.get(name="buscar")
        self.assertEqual(method.parameters, self.method.parameters)
        self.assertEqual(method.return_type, "Cliente")
        self.assertTrue(method.is_static)
        self.assertEqual(target.relations.get().label, "realiza")
        latest = target.versions.first()
        self.assertTrue(latest.is_automatic)
        self.assertEqual(len(latest.snapshot["classes"]), 2)
        self.assertEqual(len(latest.snapshot["relations"]), 1)
