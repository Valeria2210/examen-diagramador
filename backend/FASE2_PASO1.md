# Fase 2, paso 1: seleccionar el diagrama guardado

Los metadatos de persistencia y la validación del IR ya están implementados.
Continúa en [FASE2_PASO2.md](FASE2_PASO2.md) para validar y descargar el modelo.

## Inicio en esta máquina (Windows)

Python 3.13 está disponible mediante `py -3.13` y el entorno del proyecto está
en `.venv`, con las dependencias instaladas. Desde la raíz del proyecto:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File backend/start-local.ps1
```

Este script inicia Django en `http://127.0.0.1:8000`, usa PostgreSQL y establece
`DEBUG=True` para evitar el valor global incompatible `DEBUG=release`.
En el IDE, selecciona `.venv\Scripts\python.exe` como intérprete Python.
La conexión fue verificada: 2 diagramas guardados, sin migraciones pendientes,
y consultas autenticadas al listado y al detalle con respuesta HTTP 200.

En el diagramador, abre **Backend · Fase 2**. El selector consulta los diagramas
del usuario autenticado y carga el modelo completo desde la API Django y su base
de datos configurada. Incluye clases, atributos, métodos y relaciones; permite
descargar el JSON. El listado respeta la paginación y los permisos existentes.

## PostgreSQL local

Configura `backend/.env` con `DB_ENGINE=postgres` y los valores `DB_NAME`,
`DB_USER`, `DB_PASSWORD`, `DB_HOST` y `DB_PORT` de tu PostgreSQL. Para el servicio
incluido en `docker-compose.yml`, los valores deben coincidir con su configuración.
No cambies a PostgreSQL suponiendo que migra los diagramas de SQLite: son bases
independientes y los datos existentes requieren una transferencia explícita.

Desde `backend`, con las dependencias de `requirements.txt` instaladas:

```powershell
docker compose up -d
python manage.py migrate
python manage.py runserver
```

Desde `frontend`: `npm run dev`. La API predeterminada es
`http://127.0.0.1:8000/api`; se puede ajustar con `VITE_API_URL`.

## Comprobar la selección en Postman

1. `POST http://127.0.0.1:8000/api/auth/login/` con JSON
   `{"username":"tu_usuario","password":"tu_clave"}`.
2. Copia el `token` de la respuesta. Usa el encabezado
   `Authorization: Token <token>` en las siguientes peticiones.
3. `GET http://127.0.0.1:8000/api/diagrams/`. Elige un `id` de `results`;
   sigue `next` si hay más páginas.
4. `GET http://127.0.0.1:8000/api/diagrams/<id>/full/`. Comprueba el nombre,
   las clases y las relaciones contra el modelo que dibujaste.

Un usuario sin autenticación recibe 401; un diagrama ajeno sin acceso devuelve
404. Una lista vacía requiere crear un diagrama en esa base de datos.

Este paso todavía no genera Java ni un ZIP Spring Boot. El siguiente paso será
añadir metadatos de persistencia (PK, nulabilidad, unicidad y nombres de campos
de relación), construir y validar el IR descrito en la propuesta, y después
generar las capas y las peticiones Postman del sistema resultante.
