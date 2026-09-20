# Backend del Diagramador UML (Fase 1) — Django + DRF + PostgreSQL

Este es el backend del **diagramador colaborativo** (no confundir con el backend Spring Boot
que se generará en la Fase 2 a partir del diagrama). Expone una API REST para crear
proyectos, diagramas, clases UML (con atributos y métodos) y relaciones.

Ya fue probado de punta a punta (crear proyecto → diagrama → clases → atributos →
métodos → relación → leer el diagrama completo). Los pasos de abajo lo levantan igual
en tu máquina.

## 1. Requisitos previos

- Python 3.11+
- Docker y Docker Compose (para levantar PostgreSQL sin instalarlo a mano)
- Postman

## 2. Pasos para levantarlo localmente

```bash
# 1. Entrar a la carpeta del proyecto
cd backend

# 2. Crear y activar entorno virtual
python3 -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Copiar variables de entorno
cp .env.example .env

# 5. Levantar PostgreSQL con Docker
docker compose up -d

# 6. Generar y aplicar las migraciones (contra Postgres)
python manage.py makemigrations
python manage.py migrate

# 7. Crear un usuario administrador (opcional, para entrar a /admin/)
python manage.py createsuperuser

# 8. Levantar el servidor
python manage.py runserver
```

El servidor queda disponible en `http://127.0.0.1:8000/`.
Panel admin: `http://127.0.0.1:8000/admin/`.

> Nota: si en algún momento querés probar rápido sin Docker/Postgres, podés forzar
> sqlite temporalmente con `DB_ENGINE=sqlite python manage.py runserver` (solo para
> pruebas locales, no para el proyecto real).

## 3. Endpoints disponibles

Base: `http://127.0.0.1:8000/api/`

| Método | Endpoint | Descripción |
|---|---|---|
| GET/POST | `/api/projects/` | Listar / crear proyectos |
| GET/PUT/DELETE | `/api/projects/{id}/` | Ver / editar / borrar un proyecto |
| POST | `/api/projects/{id}/share/` | Crear invitación con permiso `VIEWER` o `EDITOR` |
| GET | `/api/projects/{id}/shares/` | Listar invitaciones del propietario |
| POST | `/api/projects/{id}/revoke_share/` | Revocar una invitación |
| POST | `/api/shares/{token}/accept/` | Aceptar una invitación autenticado |
| GET/POST | `/api/projects/{id}/members/` | Consultar o administrar colaboradores y roles |
| GET/POST | `/api/diagrams/` | Listar / crear diagramas |
| GET | `/api/diagrams/{id}/full/` | **Diagrama completo**: clases + atributos + métodos + relaciones (es el JSON que alimentará el generador de la Fase 2) |
| GET/POST | `/api/classes/?diagram={id}` | Listar / crear clases UML de un diagrama |
| GET/POST | `/api/attributes/?uml_class={id}` | Listar / crear atributos de una clase |
| GET/POST | `/api/methods/?uml_class={id}` | Listar / crear métodos de una clase |
| GET/POST | `/api/relations/?diagram={id}` | Listar / crear relaciones entre clases |
| POST | `/api/ai/interpret-uml/` | Interpretar texto o transcripción de voz y devolver un prototipo UML estructurado |
| GET | `/api/diagrams/{id}/analyze/` | Revisar consistencia UML: duplicados, nombres, relaciones y multiplicidades |
| GET/POST | `/api/diagrams/{id}/versions/` | Consultar o guardar versiones del diagrama |
| POST | `/api/diagrams/{id}/restore_version/` | Restaurar una versión anterior |
| POST | `/api/diagrams/{id}/import_xmi/` | Importar un XMI y crear clases, atributos, métodos y relaciones en el diagrama |
| GET | `/api/diagrams/{id}/export_ea_json/` | Descargar el modelo para el importador nativo de Enterprise Architect |
| POST | `/api/diagrams/{id}/import_image/` | Detectar clases y relaciones UML desde una imagen con OpenCV + Tesseract |

### Compartir un proyecto

Desde el frontend, selecciona un diagrama y pulsa **Compartir**. El propietario
puede crear un enlace de **Solo lectura** o **Puede editar**, copiarlo y revocarlo.
La persona invitada abre el enlace, inicia sesión o se registra y queda asociada al
proyecto. El servidor aplica el permiso en cada endpoint: los lectores consultan y
exportan, mientras que los editores también pueden modificar e importar modelos.

La colaboración sincroniza el diagrama con el servidor automáticamente cada cuatro
segundos mientras está abierto, y cada cambio se guarda en la base de datos. Los
conflictos se resuelven por última escritura aceptada por el servidor; el historial
permite recuperar una versión anterior si es necesario.

Los roles disponibles son `VIEWER` (solo lectura), `EDITOR` (edición), `SHARER`
(puede crear enlaces) y `ADMIN` (puede administrar colaboradores y enlaces). El
propietario siempre conserva todos los permisos.

### Importar un diagrama desde una imagen

El endpoint de importación de imagen usa visión clásica local: OpenCV detecta las
cajas y las líneas, y Tesseract OCR lee los nombres, atributos y métodos. No usa
IA generativa ni envía la imagen a Internet.

Además de instalar las dependencias Python con `pip install -r requirements.txt`,
Windows puede usar el ejecutable Tesseract OCR para leer nombres, atributos,
métodos y multiplicidades. Si no está en el PATH, configura en `backend/.env`
la ruta completa:

```env
TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
TESSERACT_LANG=eng
```

Desde el frontend usa **Importar imagen** o **Usar cámara**, confirma la vista previa
y selecciona un PNG/JPG/WEBP/BMP con el diagrama UML. OpenCV localiza cajas y líneas
con preprocesado adaptativo y Hough, agrupa segmentos por pares de clases y analiza
los extremos para distinguir asociación, herencia y agregación/composición cuando la
geometría es legible. También intenta leer multiplicidades cercanas con OCR. Si
Tesseract no está instalado, las cajas y relaciones siguen siendo editables y reciben
nombres genéricos (`Clase1`, `Clase2`, etc.).

Para importar un XMI exportado por este sistema o por Enterprise Architect, usa
**Importar XMI** en la barra superior. También se aceptan archivos ZIP que contengan
un XML/XMI. El archivo se procesa en dos pasadas:
primero se resuelven los IDs XML y después se crean las clases y relaciones en el
diagrama activo. Se reconocen asociaciones, agregaciones, composiciones,
herencias, realizaciones y dependencias.

### Crear un prototipo mediante voz

El botón **Voz** usa la Web Speech API del navegador para capturar la descripción
en español. La transcripción se envía al endpoint de interpretación, que usa la
herramienta estructurada `create_uml_diagram` de Claude para devolver clases,
atributos, métodos y relaciones UML 2.5+. El frontend muestra una vista previa y,
al confirmarla, crea el prototipo en el lienzo usando las acciones normales del
editor.

La clave `ANTHROPIC_API_KEY` solo se usa en el backend y nunca se envía al
navegador. Si una clave real fue compartida o quedó expuesta, revócala y genera
una nueva antes de continuar.

## 4. Probarlo en Postman — paso a paso

Podés importar el archivo `postman_collection.json` incluido (Import → File) y ya
tenés todas las peticiones armadas con variables. O armarlas a mano siguiendo este
orden (importa el orden, porque cada paso depende del `id` del anterior):

### Paso 1 — Crear un proyecto
`POST http://127.0.0.1:8000/api/projects/`
```json
{
  "name": "Sistema de Ventas",
  "description": "Proyecto demo"
}
```
Guarda el `id` que te devuelve (ej. `1`).

### Paso 2 — Crear un diagrama dentro del proyecto
`POST http://127.0.0.1:8000/api/diagrams/`
```json
{
  "project": 1,
  "name": "Diagrama principal"
}
```
Guarda el `id` del diagrama (ej. `1`).

### Paso 3 — Crear dos clases
`POST http://127.0.0.1:8000/api/classes/`
```json
{ "diagram": 1, "name": "Cliente", "kind": "CLASS", "pos_x": 100, "pos_y": 100 }
```
```json
{ "diagram": 1, "name": "Pedido", "kind": "CLASS", "pos_x": 400, "pos_y": 100 }
```
Guarda los `id` de cada clase (ej. `1` y `2`).

### Paso 4 — Agregar atributos a "Cliente"
`POST http://127.0.0.1:8000/api/attributes/`
```json
{ "uml_class": 1, "name": "nombre", "data_type": "String", "visibility": "PRIVATE" }
```
```json
{ "uml_class": 1, "name": "email", "data_type": "String", "visibility": "PRIVATE" }
```

### Paso 5 — Agregar un método a "Cliente"
`POST http://127.0.0.1:8000/api/methods/`
```json
{ "uml_class": 1, "name": "getEmail", "return_type": "String", "visibility": "PUBLIC", "parameters": [] }
```

### Paso 6 — Crear la relación Cliente (1) → Pedido (*)
`POST http://127.0.0.1:8000/api/relations/`
```json
{
  "diagram": 1,
  "source": 1,
  "target": 2,
  "relation_type": "ASSOCIATION",
  "multiplicity_source": "1",
  "multiplicity_target": "*",
  "label": "realiza"
}
```

### Paso 7 — Ver el diagrama completo
`GET http://127.0.0.1:8000/api/diagrams/1/full/`

Esto te devuelve el JSON completo del diagrama (clases, atributos, métodos y
relaciones anidados). Ese es exactamente el formato que va a leer el generador
de backend de la Fase 2.

## 8. Importar directamente en Enterprise Architect

El botón **Descargar JSON para EA** del frontend descarga un archivo JSON con el
diagrama completo. Este formato evita depender del importador XMI de EA.

En Windows, con Enterprise Architect instalado:

```powershell
cd backend
py -m pip install --user pywin32
.\tools\import_enterprise_architect.ps1 -JsonPath .\modelo.json -ProjectPath C:\modelos\diagrama.qeax
```

También puedes usar un archivo `.eapx` como destino. El script crea un paquete
con las clases, atributos, métodos, conectores y un diagrama visual que conserva
las posiciones y tamaños del lienzo. Para relaciones de herencia,
realización, composición, agregación, asociación y dependencia usa los conectores
nativos de Enterprise Architect.

El botón **Exportar XMI** genera XML XMI 2.1 para importarlo en EA desde
`Publish > Model Exchange > Import > XMI File`. Selecciona un paquete destino antes
de importar. No se debe cambiar su extensión a `.qea`:
`.qea`, `.qeax` y `.eapx` son bases de datos/proyectos nativos que solo puede crear
Enterprise Architect. Un ZIP que contenga XMI no es un proyecto QEA válido.

La revisión UML se ejecuta desde el asistente al abrir o cambiar de diagrama y también
puede lanzarse con **Revisar UML**. Devuelve hallazgos editables, pero no inventa
atributos cuyo significado no pueda inferirse con seguridad.

Este importador requiere Windows y una instalación local de Enterprise Architect;
el frontend y el backend web no necesitan Enterprise Architect para funcionar.

## 5. Valores válidos de los campos tipo "choice"

- `kind` (clase): `CLASS`, `ABSTRACT`, `INTERFACE`, `ENUM`
- `visibility` (atributo/método): `PUBLIC`, `PRIVATE`, `PROTECTED`, `PACKAGE`
- `relation_type` (relación): `ASSOCIATION`, `AGGREGATION`, `COMPOSITION`, `INHERITANCE`, `REALIZATION`, `DEPENDENCY`

## 6. Estado actual y producción

La API exige autenticación Token, salvo registro, login y el estado de salud.
Postman necesita `Authorization: Token <token>` para consultar y modificar recursos.
El frontend React está conectado y el generador Spring Boot usa los diagramas guardados.
Registro/login e interpretación por IA tienen límites de solicitudes configurables.

Para el despliegue del diagramador consulta [PRODUCCION_AWS.md](../PRODUCCION_AWS.md).
El perfil `backend.settings_production` exige secretos, PostgreSQL y HTTPS; Gunicorn
sirve Django y Caddy publica el dominio. `/api/health/` comprueba PostgreSQL.
Los Spring Boot descargados se despliegan por separado. Las limitaciones conocidas
del modelo y de las integraciones se detallan en la guía y en el informe de revisión.
