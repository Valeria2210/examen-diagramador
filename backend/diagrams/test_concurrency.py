from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth.models import User
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from rest_framework.test import APIClient

from .models import Diagram, Project, UMLClass


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentDiagramTests(TransactionTestCase):
    """Exercise actual concurrent PostgreSQL requests with independent connections."""

    def setUp(self):
        self.user = User.objects.create_user(username="concurrent-owner")
        self.project = Project.objects.create(name="Concurrent project", owner=self.user)
        self.diagram = Diagram.objects.create(name="Concurrent diagram", project=self.project)

    def run_concurrently(self, requests):
        barrier = Barrier(len(requests))

        def worker(request):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(user=User.objects.get(pk=self.user.pk))
                barrier.wait(timeout=10)
                method, url, data = request
                return getattr(client, method)(url, data, format="json").status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(requests)) as executor:
            return list(executor.map(worker, requests))

    def test_concurrent_creates_have_complete_ordered_snapshots(self):
        codes = self.run_concurrently([
            ("post", "/api/classes/", {"diagram": self.diagram.pk, "name": f"Class{index}"})
            for index in range(4)
        ])
        self.assertEqual(codes, [201] * 4)
        versions = list(self.diagram.versions.order_by("version_number"))
        self.assertEqual([item.version_number for item in versions], [1, 2, 3, 4])
        self.assertEqual([len(item.snapshot["classes"]) for item in versions], [1, 2, 3, 4])

    def test_concurrent_duplicate_class_creation_is_rejected(self):
        request = ("post", "/api/classes/", {"diagram": self.diagram.pk, "name": "Cliente"})
        self.assertEqual(sorted(self.run_concurrently([request, request])), [201, 400])
        self.assertEqual(self.diagram.classes.count(), 1)

    def test_concurrent_partial_updates_preserve_other_fields(self):
        uml_class = UMLClass.objects.create(diagram=self.diagram, name="Cliente")
        url = f"/api/classes/{uml_class.pk}/"
        self.assertEqual(self.run_concurrently([
            ("patch", url, {"name": "ClienteActualizado"}),
            ("patch", url, {"width": 420}),
        ]), [200, 200])
        uml_class.refresh_from_db()
        self.assertEqual(uml_class.name, "ClienteActualizado")
        self.assertEqual(uml_class.width, 420)

    def test_concurrent_manual_versions_have_distinct_numbers(self):
        request = ("post", f"/api/diagrams/{self.diagram.pk}/versions/", {"label": "Manual"})
        self.assertEqual(self.run_concurrently([request, request]), [201, 201])
        self.assertEqual(list(self.diagram.versions.values_list("version_number", flat=True)), [2, 1])
