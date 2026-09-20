from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Attribute, Diagram, Method, Project, ProjectMember, Relation, UMLClass


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1"])
class ResourceValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="validation-owner")
        cls.outsider = User.objects.create_user(username="validation-outsider")
        cls.project = Project.objects.create(name="Principal", owner=cls.owner)
        cls.other_project = Project.objects.create(name="Otro propio", owner=cls.owner)
        cls.private_project = Project.objects.create(name="Privado", owner=cls.outsider)
        cls.diagram = Diagram.objects.create(project=cls.project, name="Principal")
        cls.other_diagram = Diagram.objects.create(project=cls.other_project, name="Otro")
        cls.private_diagram = Diagram.objects.create(project=cls.private_project, name="Privado")
        cls.source = UMLClass.objects.create(diagram=cls.diagram, name="Cliente")
        cls.target = UMLClass.objects.create(diagram=cls.diagram, name="Pedido")
        cls.other_class = UMLClass.objects.create(diagram=cls.other_diagram, name="Producto")
        cls.private_class = UMLClass.objects.create(diagram=cls.private_diagram, name="Privada")
        cls.attribute = Attribute.objects.create(uml_class=cls.source, name="nombre")
        cls.method = Method.objects.create(uml_class=cls.source, name="guardar")
        cls.relation = Relation.objects.create(diagram=cls.diagram, source=cls.source, target=cls.target)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_existing_resources_cannot_move_even_between_owned_containers(self):
        resources = [
            ("diagrams", self.diagram, "project", self.other_project),
            ("classes", self.source, "diagram", self.other_diagram),
            ("attributes", self.attribute, "uml_class", self.target),
            ("methods", self.method, "uml_class", self.target),
            ("relations", self.relation, "diagram", self.other_diagram),
        ]
        for endpoint, instance, parent_field, destination in resources:
            with self.subTest(endpoint=endpoint):
                previous_parent = getattr(instance, f"{parent_field}_id")
                response = self.client.patch(
                    f"/api/{endpoint}/{instance.pk}/", {parent_field: destination.pk}, format="json"
                )
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(parent_field, response.data)
                instance.refresh_from_db()
                self.assertEqual(getattr(instance, f"{parent_field}_id"), previous_parent)
        self.assertFalse(self.diagram.versions.exists())

    def test_put_cannot_move_class_to_another_owned_diagram(self):
        response = self.client.put(
            f"/api/classes/{self.source.pk}/",
            {"diagram": self.other_diagram.pk, "name": "Cliente"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("diagram", response.data)

    def test_resource_cannot_move_into_another_users_project(self):
        response = self.client.patch(
            f"/api/diagrams/{self.diagram.pk}/", {"project": self.private_project.pk}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.diagram.refresh_from_db()
        self.assertEqual(self.diagram.project_id, self.project.pk)

    def test_unchanged_parent_is_allowed_on_updates(self):
        response = self.client.patch(
            f"/api/classes/{self.source.pk}/",
            {"diagram": self.diagram.pk, "name": "Cliente actualizado"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.source.refresh_from_db()
        self.assertEqual(self.source.name, "Cliente actualizado")

    def test_create_requires_a_parent_for_every_resource(self):
        for endpoint, field in [
            ("diagrams", "project"), ("classes", "diagram"),
            ("attributes", "uml_class"), ("methods", "uml_class"), ("relations", "diagram"),
        ]:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(f"/api/{endpoint}/", {"name": "Nuevo"}, format="json")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(field, response.data)

    def test_create_foreign_keys_are_limited_to_accessible_projects(self):
        payloads = [
            ("diagrams", {"name": "Nuevo", "project": self.private_project.pk}, "project"),
            ("classes", {"name": "Nuevo", "diagram": self.private_diagram.pk}, "diagram"),
            ("attributes", {"name": "nuevo", "uml_class": self.private_class.pk}, "uml_class"),
            ("methods", {"name": "nuevo", "uml_class": self.private_class.pk}, "uml_class"),
            ("relations", {"diagram": self.diagram.pk, "source": self.source.pk,
                           "target": self.private_class.pk}, "target"),
        ]
        for endpoint, payload, field in payloads:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(f"/api/{endpoint}/", payload, format="json")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(field, response.data)

    def test_relationship_endpoints_must_belong_to_its_diagram_on_create(self):
        for field in ("source", "target"):
            with self.subTest(field=field):
                payload = {"diagram": self.diagram.pk, "source": self.source.pk, "target": self.target.pk}
                payload[field] = self.other_class.pk
                response = self.client.post("/api/relations/", payload, format="json")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(field, response.data)
        self.assertEqual(Relation.objects.count(), 1)

    def test_relationship_endpoints_are_validated_on_partial_update(self):
        for field in ("source", "target"):
            with self.subTest(field=field):
                response = self.client.patch(
                    f"/api/relations/{self.relation.pk}/", {field: self.other_class.pk}, format="json"
                )
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(field, response.data)
        self.relation.refresh_from_db()
        self.assertEqual(self.relation.source_id, self.source.pk)
        self.assertEqual(self.relation.target_id, self.target.pk)

    def test_relationship_endpoints_are_validated_on_put(self):
        response = self.client.put(
            f"/api/relations/{self.relation.pk}/",
            {"diagram": self.diagram.pk, "source": self.other_class.pk, "target": self.target.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("source", response.data)

    def test_relationship_can_change_endpoint_inside_same_diagram(self):
        response = self.client.patch(
            f"/api/relations/{self.relation.pk}/", {"target": self.source.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.relation.refresh_from_db()
        self.assertEqual(self.relation.target_id, self.source.pk)

    def test_invalid_diagram_ids_return_validation_errors_instead_of_server_errors(self):
        for diagram_id in ("invalid", [], {"id": self.diagram.pk}, None):
            with self.subTest(diagram_id=diagram_id):
                response = self.client.post(
                    "/api/classes/", {"name": "Nueva", "diagram": diagram_id}, format="json"
                )
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn("diagram", response.data)

    def test_class_names_are_unique_ignoring_case_and_repeated_whitespace(self):
        UMLClass.objects.create(diagram=self.diagram, name="Orden de Compra")
        response = self.client.post(
            "/api/classes/", {"diagram": self.diagram.pk, "name": "  ORDEN   de  compra  "}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("name", response.data)
        renamed = self.client.patch(
            f"/api/classes/{self.source.pk}/", {"name": " pedido "}, format="json"
        )
        self.assertEqual(renamed.status_code, 400, renamed.data)
        self.source.refresh_from_db()
        self.assertEqual(self.source.name, "Cliente")

    def test_same_class_name_is_allowed_in_other_diagrams(self):
        response = self.client.post(
            "/api/classes/", {"diagram": self.other_diagram.pk, "name": self.source.name}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_geometry_rejects_non_finite_values(self):
        for field in ("pos_x", "pos_y", "width", "height"):
            for value in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(field=field, value=value):
                    response = self.client.patch(
                        f"/api/classes/{self.source.pk}/", {field: value}, format="json"
                    )
                    self.assertEqual(response.status_code, 400, response.data)
                    self.assertIn(field, response.data)
        self.assertFalse(self.diagram.versions.exists())

    def test_geometry_requires_positive_dimensions_but_allows_negative_positions(self):
        for field in ("width", "height"):
            for value in (0, -1):
                with self.subTest(field=field, value=value):
                    response = self.client.patch(
                        f"/api/classes/{self.source.pk}/", {field: value}, format="json"
                    )
                    self.assertEqual(response.status_code, 400, response.data)
        response = self.client.patch(
            f"/api/classes/{self.source.pk}/",
            {"pos_x": -100, "pos_y": -20.5, "width": 220.5, "height": 140},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

    def test_method_parameters_reject_invalid_structures_and_types(self):
        invalid_parameters = [
            {}, "id: Long", None, ["id"], [None], [[]], [{}],
            [{"name": "id"}], [{"type": "Long"}], [{"name": 1, "type": "Long"}],
            [{"name": "id", "type": False}], [{"name": " ", "type": "Long"}],
            [{"name": "id", "type": ""}], [{"name": "id", "type": "X" * 101}],
        ]
        for parameters in invalid_parameters:
            with self.subTest(parameters=parameters):
                response = self.client.patch(
                    f"/api/methods/{self.method.pk}/", {"parameters": parameters}, format="json"
                )
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn("parameters", response.data)
        self.method.refresh_from_db()
        self.assertEqual(self.method.parameters, [])

    def test_method_parameters_round_trip_and_can_be_cleared(self):
        parameters = [{"name": "id", "type": "Long"}, {"name": "items", "type": "List<Item>"}]
        created = self.client.post(
            "/api/methods/", {"uml_class": self.source.pk, "name": "buscar", "parameters": parameters},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["parameters"], parameters)
        cleared = self.client.patch(
            f"/api/methods/{created.data['id']}/", {"parameters": []}, format="json"
        )
        self.assertEqual(cleared.status_code, 200, cleared.data)
        self.assertEqual(cleared.data["parameters"], [])

    def test_attribute_and_method_order_cannot_be_negative(self):
        for endpoint, instance in [("attributes", self.attribute), ("methods", self.method)]:
            with self.subTest(endpoint=endpoint):
                response = self.client.patch(
                    f"/api/{endpoint}/{instance.pk}/", {"order": -1}, format="json"
                )
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn("order", response.data)

    def test_shared_editor_can_create_related_resources(self):
        ProjectMember.objects.create(project=self.project, user=self.outsider, role="EDITOR")
        self.client.force_authenticate(user=self.outsider)
        response = self.client.post(
            "/api/attributes/", {"uml_class": self.source.pk, "name": "activo"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_full_diagram_reports_current_access_role(self):
        owner = self.client.get(f"/api/diagrams/{self.diagram.pk}/full/")
        self.assertEqual(owner.status_code, 200, owner.data)
        self.assertEqual(owner.data["access_role"], "OWNER")
        ProjectMember.objects.create(project=self.project, user=self.outsider, role="SHARER")
        self.client.force_authenticate(user=self.outsider)
        shared = self.client.get(f"/api/diagrams/{self.diagram.pk}/full/")
        self.assertEqual(shared.status_code, 200, shared.data)
        self.assertEqual(shared.data["access_role"], "SHARER")
