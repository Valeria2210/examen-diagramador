import json


class PostmanConverter:
    """Convert the generator's OpenAPI subset to Postman v2.1 without a server."""
    def __init__(self, openapi_spec, nombre_coleccion):
        self.spec, self.nombre = openapi_spec, nombre_coleccion

    def ejemplo(self, name, field):
        if field.get("type") == "array":
            return []
        if "example" in field:
            return field["example"]
        formats = {"date": "2026-01-15", "date-time": "2026-01-15T10:30:00",
            "uuid": "00000000-0000-0000-0000-000000000001"}
        value = formats.get(field.get("format"), {"string": "ejemplo_" + name,
            "integer": 1, "number": 99.99, "boolean": True}.get(field["type"]))
        return value[:field["maxLength"]] if isinstance(value, str) and "maxLength" in field else value

    def convertir(self):
        groups, variables = {}, {}
        for path, operations in self.spec["paths"].items():
            for method, op in operations.items():
                tag = op["tags"][0]
                variable = tag.lower() + "_id"
                if "{id}" in path:
                    variables[variable] = ""
                url = "{{base_url}}" + path.replace("{id}", "{{" + variable + "}}")
                request = {"method": method.upper(), "url": url, "header": []}
                if "requestBody" in op:
                    ref = op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
                    props = self.spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]["properties"]
                    body = {n: self.ejemplo(n, f) for n, f in props.items()
                        if not f.get("readOnly") and not f.get("x-generated-id")}
                    request["header"] = [{"key": "Content-Type", "value": "application/json"}]
                    request["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2, ensure_ascii=False),
                        "options": {"raw": {"language": "json"}}}
                item = {"name": op["summary"], "request": request}
                if method == "post" and "x-id-field" in op:
                    item["event"] = [{"listen": "test", "script": {"type": "text/javascript", "exec": [
                        "pm.test('Creado', () => pm.response.to.have.status(201));",
                        "if (pm.response.code === 201) pm.collectionVariables.set(" + json.dumps(variable) +
                        ", pm.response.json()[" + json.dumps(op["x-id-field"]) + "]);" ]}}]
                elif op.get("x-store-token"):
                    item["event"] = [{"listen": "test", "script": {"type": "text/javascript", "exec": [
                        "pm.test('Autenticación correcta', () => pm.expect(pm.response.code).to.be.oneOf([200, 201]));",
                        "if ([200, 201].includes(pm.response.code)) pm.collectionVariables.set('access_token', pm.response.json().token);" ]}}]
                groups.setdefault(tag, []).append(item)
        return {"info": {"name": self.nombre,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
            "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}]},
            "variable": [{"key": "base_url", "value": self.spec["servers"][0]["url"]},
                {"key": "access_token", "value": ""},
                *[{"key": k, "value": v} for k, v in variables.items()]],
            "item": [{"name": tag, "item": items} for tag, items in groups.items()]}
