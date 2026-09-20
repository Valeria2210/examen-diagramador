"""Write the standalone Postman collection without any stored credentials."""
import json
from pathlib import Path

items = []
for name, method, path, body in [
    ("1 - Validar IR", "POST", "validar/", {"diagrama_id": "{{diagrama_id}}"}),
    ("2 - Preparar ZIP", "POST", "generar-backend/", {"diagrama_id": "{{diagrama_id}}", "incluir_swagger": True, "incluir_docker": True}),
    ("3 - Descargar ZIP", "GET", "descargar/{{nombre_archivo}}/", None),
    ("4 - Historial", "GET", "historial/", None),
]:
    request = {"method": method, "header": [{"key": "Authorization", "value": "Token {{token}}"}],
               "url": "{{base_url}}/api/generador/" + path}
    if body:
        request["header"].append({"key": "Content-Type", "value": "application/json"})
        request["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2), "options": {"raw": {"language": "json"}}}
    item = {"name": name, "request": request}
    if name.startswith("2"):
        item["event"] = [{"listen": "test", "script": {"type": "text/javascript", "exec": [
            "pm.test('Preparación exitosa', () => pm.response.to.have.status(201));",
            "if (pm.response.code === 201) {",
            "  const data = pm.response.json();",
            "  pm.collectionVariables.set('nombre_archivo', data.zip_url.split('/').filter(Boolean).pop());",
            "}",
        ]}}]
    items.append(item)
collection = {"info": {"name": "Fase 2 - IR y descarga protegida",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
    "variable": [{"key": key, "value": value} for key, value in
        [("base_url", "http://127.0.0.1:8000"), ("token", ""), ("diagrama_id", "1"), ("nombre_archivo", "")]], "item": items}
Path(__file__).with_name("postman_fase2_collection.json").write_text(json.dumps(collection, indent=2), encoding="utf-8")
