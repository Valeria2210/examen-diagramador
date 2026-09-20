"""Extra HTTP assertions for step5-relations (dedicated disposable demo API)."""
import uuid
import smoke_generated
from smoke_generated import request, run


def ensure_authenticated():
    if not smoke_generated.TOKEN:
        smoke_generated.authenticate()


def simple_crud():
    ensure_authenticated()
    value = request("POST", "/api/clientes", {"nombre": "CRUD sin relaciones"}, 201)
    key = value["codigoCliente"]
    assert request("GET", f"/api/clientes/{key}")["nombre"] == "CRUD sin relaciones"
    assert request("PUT", f"/api/clientes/{key}", {"nombre": "Actualizado"})["nombre"] == "Actualizado"
    request("DELETE", f"/api/clientes/{key}", expected=204)
    request("GET", f"/api/clientes/{key}", expected=404)
    print("PASS: CRUD simple antes de probar relaciones.")


def collections():
    ensure_authenticated()
    tag = uuid.uuid4().hex[:12]
    codes = [tag + "a", tag + "b"]
    for code in codes:
        request("POST", "/api/etiquetas", {"codigo": code, "nombre": code}, 201)
    body = {"total": 10, "etiquetasIds": [codes[1], codes[0], codes[1]]}
    pedido = request("POST", "/api/pedidos", body, 201)
    key = pedido["codigoPedido"]
    assert set(pedido["etiquetasIds"]) == set(codes) and len(pedido["etiquetasIds"]) == 2
    for code in codes:
        assert key in request("GET", f"/api/etiquetas/{code}")["pedidosIds"]
    request("PUT", f"/api/pedidos/{key}", {"total": 99, "etiquetasIds": [codes[0], "missing-" + tag]}, 404)
    after = request("GET", f"/api/pedidos/{key}")
    assert after["total"] == 10 and set(after["etiquetasIds"]) == set(codes)
    assert request("PUT", f"/api/pedidos/{key}", {"total": 20})["etiquetasIds"]
    assert request("PUT", f"/api/pedidos/{key}", {"total": 20, "etiquetasIds": []})["etiquetasIds"] == []
    for code in codes:
        assert key not in request("GET", f"/api/etiquetas/{code}")["pedidosIds"]
    request("DELETE", f"/api/pedidos/{key}", expected=204)
    for code in codes:
        request("DELETE", f"/api/etiquetas/{code}", expected=204)
    print("PASS: N-N con dos IDs, duplicados, ID inexistente, rollback, omisión y vaciado.")


def one_to_one():
    ensure_authenticated()
    perfil = request("POST", "/api/perfils", {"descripcion": "Unicidad 1-1"}, 201)
    key = perfil["clavePerfil"]
    cliente = request("POST", "/api/clientes", {"nombre": "Propietario 1-1", "perfilId": key}, 201)
    cid = cliente["codigoCliente"]
    request("POST", "/api/clientes", {"nombre": "Otro propietario", "perfilId": key}, 409)
    request("DELETE", f"/api/perfils/{key}", expected=409)
    assert request("GET", f"/api/perfils/{key}")["clienteId"] == cid
    request("PUT", f"/api/clientes/{cid}", {"nombre": "Desvinculado", "perfilId": None})
    assert request("GET", f"/api/perfils/{key}")["clienteId"] is None
    request("DELETE", f"/api/clientes/{cid}", expected=204)
    request("DELETE", f"/api/perfils/{key}", expected=204)
    print("PASS: 1-1 con unicidad, borrado protegido y desvinculación.")


if __name__ == "__main__":
    simple_crud()
    run()
    collections()
    one_to_one()
