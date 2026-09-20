"""Read-only verification of the configured diagram database and API."""
from django.db import connection
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from diagrams.models import Diagram

connection.ensure_connection()
print("Database engine:", connection.vendor)
print("Saved diagrams:", Diagram.objects.count())
diagram = Diagram.objects.select_related("project__owner").filter(project__owner__isnull=False).first()
if diagram:
    client = APIClient()
    client.force_authenticate(user=diagram.project.owner)
    response = client.get("/api/diagrams/", HTTP_HOST="localhost")
    print("Diagram list HTTP:", response.status_code)
    assert response.status_code == 200
    response = client.get(f"/api/diagrams/{diagram.pk}/full/", HTTP_HOST="localhost")
    print("Full diagram HTTP:", response.status_code)
    assert response.status_code == 200
    print("Classes:", len(response.data["classes"]), "Relations:", len(response.data["relations"]))
else:
    print("No owned diagram available for authenticated API verification.")
