"""Offline API contract derived from the prepared IR used by Java templates."""
import copy


class OpenAPIBuilder:
    def __init__(self, ir):
        self.ir = ir

    @staticmethod
    def tipo(tipo):
        types = {
            "String": ("string", None), "Long": ("integer", "int64"),
            "Integer": ("integer", "int32"), "Boolean": ("boolean", None),
            "BigDecimal": ("number", None), "Double": ("number", "double"),
            "Float": ("number", "float"), "UUID": ("string", "uuid"),
            "LocalDate": ("string", "date"), "LocalDateTime": ("string", "date-time"),
        }
        kind, fmt = types[tipo]
        return {"type": kind, **({"format": fmt} if fmt else {})}

    def construir(self):
        schemas, paths = {}, {}
        for e in self.ir["entidades"]:
            props, required = {}, []
            for a in e["atributos"]:
                field = self.tipo(a["tipo"])
                field["nullable"] = a["nullable"] or (a["pk"] and a["autogenerado"])
                if a["longitud"]:
                    field["maxLength"] = a["longitud"]
                if a["pk"]:
                    field["x-generated-id"] = a["autogenerado"]
                if not a["nullable"] and not a["pk"]:
                    required.append(a["nombre"])
                props[a["nombre"]] = field
            for r in e["relaciones"]:
                field = self.tipo(r["id_tipo"])
                if r["many"]:
                    field = {"type": "array", "items": field}
                else:
                    field["nullable"] = True
                    field["example"] = None
                field["readOnly"] = not r["owner"]
                props[r["dto_campo"]] = field
            schemas[e["nombre"] + "DTO"] = {"type": "object", "properties": props,
                **({"required": required} if required else {})}
            ref = {"$ref": "#/components/schemas/" + e["nombre"] + "DTO"}
            operations = {}
            for method, label, status in (("post", "Crear", "201"), ("get", "Listar", "200"),
                    ("put", "Actualizar", "200"), ("delete", "Eliminar", "204"), ("find", "Buscar", "200")):
                schema = ({"type": "object", "properties": {
                    "content": {"type": "array", "items": ref}, "number": {"type": "integer"},
                    "size": {"type": "integer"}, "totalElements": {"type": "integer", "format": "int64"},
                    "totalPages": {"type": "integer"}, "first": {"type": "boolean"}, "last": {"type": "boolean"}
                }} if label == "Listar" else ref)
                response = {"description": label}
                if method != "delete":
                    response["content"] = {"application/json": {"schema": schema}}
                op = {"tags": [e["nombre"]], "summary": label, "responses": {status: response}}
                if method in ("put", "delete", "find"):
                    op["parameters"] = [{"name": "id", "in": "path", "required": True,
                        "schema": self.tipo(e["pk"]["tipo"])}]
                    op["responses"]["404"] = {"description": "Recurso no encontrado"}
                if method in ("post", "put"):
                    op["requestBody"] = {"required": True, "content": {"application/json": {"schema": copy.deepcopy(ref)}}}
                    op["responses"]["400"] = {"description": "Datos inválidos"}
                if method == "post":
                    op["x-id-field"] = e["pk"]["nombre"]
                if label == "Listar":
                    op["parameters"] = [
                        {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 0, "default": 0}},
                        {"name": "size", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}},
                        {"name": "sort", "in": "query", "schema": {"type": "string"}}
                    ]
                operations[method] = op
            route = "/api/" + e["ruta"]
            paths[route] = {m: operations[m] for m in ("post", "get")}
            paths[route + "/{id}"] = {"get": operations["find"], **{m: operations[m] for m in ("put", "delete")}}
        schemas.update({
            "RegisterRequest": {"type": "object", "required": ["username", "password"], "properties": {
                "username": {"type": "string", "minLength": 3, "maxLength": 100, "example": "flutter_user"},
                "password": {"type": "string", "format": "password", "minLength": 10, "maxLength": 72, "example": "local-password-123"}}},
            "LoginRequest": {"type": "object", "required": ["username", "password"], "properties": {
                "username": {"type": "string", "example": "admin"},
                "password": {"type": "string", "format": "password", "example": "change-this-local-password"}}},
            "TokenResponse": {"type": "object", "properties": {
                "token": {"type": "string"}, "tokenType": {"type": "string", "example": "Bearer"},
                "expiresAt": {"type": "string", "format": "date-time"}, "username": {"type": "string"},
                "role": {"type": "string", "enum": ["USER", "ADMIN"]}}},
            "UserResponse": {"type": "object", "properties": {
                "username": {"type": "string"}, "role": {"type": "string", "enum": ["USER", "ADMIN"]}}},
        })
        def ref(name):
            return {"$ref": "#/components/schemas/" + name}
        def json_body(name):
            return {"required": True, "content": {"application/json": {"schema": ref(name)}}}
        def json_response(description, name=None):
            response = {"description": description}
            if name:
                response["content"] = {"application/json": {"schema": ref(name)}}
            return response
        paths.update({
            "/api/auth/register": {"post": {"tags": ["Auth"], "summary": "Registrar usuario", "security": [],
                "requestBody": json_body("RegisterRequest"), "responses": {"201": json_response("Usuario registrado", "TokenResponse"),
                    "400": {"description": "Datos inválidos"}, "409": {"description": "El usuario ya existe"}}, "x-store-token": True}},
            "/api/auth/login": {"post": {"tags": ["Auth"], "summary": "Iniciar sesión", "security": [],
                "requestBody": json_body("LoginRequest"), "responses": {"200": json_response("Sesión iniciada", "TokenResponse"),
                    "400": {"description": "Datos inválidos"}, "401": {"description": "Credenciales inválidas"}}, "x-store-token": True}},
            "/api/auth/logout": {"post": {"tags": ["Auth"], "summary": "Cerrar sesión",
                "responses": {"204": {"description": "Sesión cerrada"}}}},
            "/api/auth/me": {"get": {"tags": ["Auth"], "summary": "Usuario actual",
                "responses": {"200": json_response("Usuario autenticado", "UserResponse"), "401": {"description": "No autenticado"}}}},
        })
        return {"openapi": "3.0.3", "info": {"title": self.ir["proyecto"]["nombre"], "version": "1.0.0"},
            "servers": [{"url": "http://localhost:8080"}], "paths": paths,
            "security": [{"BearerAuth": []}], "components": {"schemas": schemas,
                "securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}}}}
