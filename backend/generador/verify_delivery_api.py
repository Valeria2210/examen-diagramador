"""Check the dedicated final demo API using the generated bearer authentication."""
import os
import time
from http.client import RemoteDisconnected
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import smoke_generated
from smoke_generated import BASE
from smoke_step5 import simple_crud, run, collections, one_to_one

for attempt in range(40):
    try:
        with urlopen(BASE + "/v3/api-docs", timeout=2):
            break
    except (URLError, TimeoutError, RemoteDisconnected, ConnectionError):
        time.sleep(1)
else:
    raise RuntimeError("El backend de entrega no está disponible.")

for path in ("/api/clientes", "/api;test/clientes"):
    for headers in ({}, {"Authorization": "Bearer incorrecto"}):
        try:
            urlopen(Request(BASE + path, headers=headers), timeout=10)
            raise AssertionError("La API debe rechazar solicitudes sin autenticación válida.")
        except HTTPError as error:
            assert error.code == 401
print("PASS: token ausente/incorrecto responde 401.")
smoke_generated.authenticate()
simple_crud()
run()
collections()
one_to_one()
