# Revisión del diagramador: seguridad y arquitectura

Fecha: 18/09/2026. Alcance: React/TypeScript, Django REST Framework,
permisos de proyectos, historial, importación/exportación y configuración Docker
de producción. El backend Spring Boot generado se revisó por separado.

## Dictamen

La arquitectura es razonable para un monolito pequeño: frontend React, API Django,
PostgreSQL y proxy HTTPS. Hay separación en modelos, serializers, parsers y
generador. La autorización básica está implementada en el servidor y tiene
pruebas. Sin embargo, existe un fallo reproducido que permite recuperar permisos
administrativos tras una degradación, además de carencias en revocación de
colaboradores, protección de tareas costosas y conservación de datos XMI.
No corresponde afirmar que todo está correcto solo porque las pruebas pasan.

## Hallazgos priorizados

### 1. Alta: reutilizar una invitación restaura permisos retirados

Ubicación: `backend/diagrams/views.py:318`, especialmente la condición de la línea 330.

Reproducción en una base SQLite en memoria:

1. El propietario crea un enlace de rol ADMIN y un colaborador lo acepta.
2. El propietario cambia el rol de ese colaborador a VIEWER mediante `members`.
3. El colaborador vuelve a aceptar el mismo enlace activo.
4. Su membresía vuelve a ADMIN.

La condición `share.role == "ADMIN"` sobrescribe la membresía existente; la otra
condición permite también aumentar el rol de un VIEWER. Se comprueba que el
emisor todavía puede conceder permisos, pero no se respeta la decisión posterior
de degradar al destinatario. No exige adivinar un UUID: basta conservar una
invitación recibida legítimamente.

Corrección: hacer que aceptar una invitación sea idempotente para una membresía
existente. Los cambios de rol posteriores deben realizarse mediante la acción de
administración de miembros. Si se necesitan nuevas invitaciones para aumentar
permisos, vincularlas a destinatario y a una autorización nueva explícita.
Añadir una prueba que exija conservar VIEWER al reutilizar el enlace antiguo.

### 2. Media: no existe revocación completa de colaboradores

Ubicación: `backend/diagrams/views.py:282` y acción `members` desde la línea 298.

`revoke_share` desactiva el enlace, pero no elimina las membresías creadas al
aceptarlo. La reproducción obtuvo HTTP 200 al leer el diagrama y HTTP 201 al
crear una clase después de revocar el enlace. Esto puede ser válido para una
invitación, pero debe distinguirse claramente de retirar acceso al proyecto.

La API de miembros permite consultar y cambiar roles, pero no expulsar a un
colaborador. Cambiarlo a VIEWER conserva acceso a todo el modelo. El diálogo
de compartir solo administra enlaces.

Corrección: añadir una operación autorizada para eliminar membresías y una
interfaz de colaboradores; aclarar que revocar una invitación impide nuevas
aceptaciones. Evitar borrar indiscriminadamente membresías al revocar enlaces,
porque un usuario puede haber recibido acceso por otra vía.

### 3. Media: OCR e importaciones carecen de controles de coste propios

Ubicación: `backend/diagrams/views.py:205`, `:626`, `:645`;
`backend/diagrams/image_import.py:145`, `:293`, `:392`.

Login, IA textual y generación tienen throttles; los endpoints de importación
y OCR no los declaran y tampoco existe un throttle global. Tesseract se ejecuta
sin timeout explícito por llamada. Las imágenes se verifican con Pillow, pero no
hay un máximo propio de píxeles, candidatos OCR o tiempo total de procesamiento.

El parser XMI sí limita la entrada y el total XML descomprimido a 16 MiB. Caddy
limita el cuerpo HTTP a 20 MB. Son medidas útiles: no se encontró una extracción
ZIP a rutas controladas por el usuario. Aun así, los endpoints leen el archivo
completo antes del límite del parser y el proxy no limita el trabajo OCR.
Gunicorn tiene un timeout global, que no equivale a un presupuesto por operación.

Corrección: limitar `uploaded.size` antes de leer, dimensiones de imagen y
cantidad de clases/miembros; aplicar throttles a importaciones y timeouts a OCR.
Para cargas grandes, ejecutar OCR y tareas externas en trabajos de fondo con
límites y estado consultable. La explotación por agotamiento de recursos no se
probó mediante cargas masivas.

### 4. Media: tokens persistentes accesibles desde JavaScript

Ubicación: `frontend/src/api.ts:70`, `frontend/src/App.tsx:146`;
`backend/diagrams/views.py:70`, `backend/backend/settings.py`.

Se guarda el token en localStorage. Login reutiliza el mismo token y la
autenticación configurada no implementa caducidad. Logout elimina el token
compartido del usuario y cierra sus demás dispositivos.

Esto amplía el impacto de una eventual ejecución de JavaScript malicioso.
No se encontró un uso de `dangerouslySetInnerHTML` o `eval` en el código
revisado, ni se demostró una vulnerabilidad XSS. La falta de CSRF en llamadas
con Token en Authorization no debe confundirse con un fallo de sesiones.

Corrección: definir duración, renovación y revocación por sesión/dispositivo;
considerar sesiones mediante cookies HttpOnly para el despliegue del mismo
origen, incorporando CSRF. Una CSP sería defensa adicional; no sustituye
validación ni obliga a asumir que exista XSS.

### 5. Media: exportar e importar XMI pierde metadatos persistentes

Ubicación: `backend/diagrams/xmi_export.py:103`;
`backend/diagrams/views.py:678` y parser XMI.

Un atributo String `codigo`, PK, único, no nullable y longitud 20 vuelve de la
conversión XMI solo con nombre, tipo, visibilidad y static. Se pierden `es_pk`,
`es_unico`, `nullable` y `longitud`; los nombres personalizados de los campos
de relación tampoco se conservan. Esto cambia el modelo usado después para
generar el backend.

Corrección: definir extensiones/tagged values XMI para estos metadatos y probar
el ciclo completo de exportar/importar. Si el formato es solo conceptual,
explicar la pérdida y ofrecer un formato nativo de respaldo completo.

### 6. Media: importación por imagen puede dejar cambios parciales

Ubicación: `frontend/src/App.tsx:532`.

El frontend crea clases, atributos, métodos y relaciones mediante peticiones
sucesivas. Si una petición intermedia falla, las anteriores ya están guardadas.
`withSaving` muestra el error y recarga el modelo; no revierte los cambios.
El flujo del asistente también debe revisarse al unificar las importaciones.

Corrección: enviar el modelo validado a un endpoint de importación transaccional
y devolver el diagrama actualizado. Mantener la vista previa en el frontend.
El importador XMI que escribe datos ya usa una transacción, lo que es una buena
base para esa operación. Este hallazgo se deriva del flujo del código; no se
simuló un corte de red en un navegador.

## Arquitectura: mejoras con impacto

- `diagrams/views.py` concentra autenticación, integración de IA, permisos,
  historial, copia, restauración y persistencia de importaciones. Extraer servicios
  de colaboración, versionado e importación facilitará pruebas y correcciones.
  No hace falta introducir microservicios para el tamaño actual.
- Cada mutación serializa un snapshot completo y mantiene bloqueado el diagrama.
  Se conservan hasta 100 snapshots automáticos; los manuales no tienen cuota.
  Arrastrar clases y editar miembros puede aumentar significativamente el trabajo
  y almacenamiento. Agrupar cambios y limitar tamaño e historial por proyecto.
- La lista de diagramas hace prefetch de todas sus clases, atributos, métodos y
  relaciones aunque el serializer de lista no los devuelve. Reservar esa carga
  para `full`, exportaciones y operaciones que necesitan el modelo completo.
- El frontend consulta el modelo completo cada cuatro segundos cuando está
  inactivo. Añadir una revisión/ETag para evitar transferir datos sin cambios.
- El bloqueo de filas serializa escrituras y protege versiones, pero no informa
  a un editor de que está guardando sobre datos obsoletos. Incorporar una revisión
  esperada del modelo para detectar conflictos en edición colaborativa.
- El cache de throttling de producción usa archivos. Los throttles estándar no
  son atómicos ni una protección completa contra denegación de servicio.
  Para varias réplicas hacen falta controles compartidos adecuados y límites
  en proxy/plataforma. [Documentación oficial de DRF](https://www.django-rest-framework.org/api-guide/throttling/).

## Defensas existentes y límites de la revisión

- Consultas filtradas por propietario/miembro y controles de rol en el servidor.
- Contenedores de recursos inmutables y relaciones limitadas al mismo diagrama.
- Validación de contraseñas y hashing de Django; mensajes genéricos de login.
- Transacciones, snapshots y restricciones únicas para miembros y versiones.
- ORM para las operaciones revisadas; no se encontró SQL construido a partir
  de entrada de usuario. El healthcheck usa un SQL constante y no expone detalles.
- Configuración de producción separada, DEBUG desactivado, secretos obligatorios,
  hosts concretos, cookies seguras y HTTPS. El backend no publica su puerto en
  Compose; solo el proxy publica 80/443. El contenedor Django usa un usuario
  sin privilegios y excluye `.env`, entornos virtuales y artefactos al copiar.

El parser acepta entidades XML internas: se reprodujo una entidad pequeña y
benigna en un nombre de clase. Esto no demuestra XXE ni lectura de archivos:
ElementTree no expande entidades externas. Conviene rechazar DTD/entidades si
no son parte del contrato y revisar límites y versión de Expat.
[Documentación oficial de Python](https://docs.python.org/3/library/xml.html).

Los controles de permisos se comprueban antes de algunas transacciones; las
carreras entre retirar un permiso y una operación en curso necesitan pruebas
específicas. No se presenta esa posibilidad como explotación confirmada.

## Entornos y verificaciones

Hay dos entornos virtuales. `backend/start-local.ps1` utiliza `examen/.venv`,
que tiene Django 5.2.17, DRF 3.17.2, Pillow 12.3.0 y Jinja2 3.1.6, coincidentes
con requirements.txt. `examen/backend/.venv` contiene Django 5.0.6, DRF 3.15.2
y Pillow 11.0.0. No atribuir esas versiones antiguas al despliegue actual:
son un entorno secundario que conviene retirar o sincronizar tras comprobar usos.
Django 5.0 terminó soporte en abril de 2025 y 5.0.6 no incluye correcciones
posteriores. [Soporte oficial](https://www.djangoproject.com/download/),
[correcciones de 5.0.7](https://docs.djangoproject.com/en/dev/releases/5.0.7/).

| Verificación de esta revisión | Resultado |
|---|---|
| Build React/TypeScript y Vite | Correcto |
| Pruebas de exportación y entrega del frontend | 8 aprobadas |
| `npm audit --json` | 0 vulnerabilidades informadas |
| Django en SQLite, entorno de arranque | 105 aprobadas y 4 omitidas por concurrencia |
| Django en PostgreSQL, entorno de arranque, base temporal de nombre único | 109 aprobadas, incluidas las 4 de concurrencia |
| Reproducción de hallazgos, ambos entornos | ADMIN recuperable, acceso tras revocar y pérdida XMI confirmados |
| `manage.py check` | Sin incidencias |
| `makemigrations --check --dry-run`, ambos entornos | Sin migraciones nuevas pendientes |
| `check --deploy`, configuración de prueba, ambos entornos | Solo avisos W005 y W021 sobre subdominios/preload HSTS |

Los avisos HSTS no implican activar esas opciones sin comprobar los dominios.
La comprobación de producción usó valores de prueba, no verifica el servidor
publicado, los certificados ni los secretos reales. No se ejecutó una auditoría
completa de dependencias Python ni un pentest del despliegue.

La reproducción está en `backend/tools/review_diagramador.py`; utiliza SQLite
en memoria y no modifica la base ni los diagramas reales. Se añadieron este
informe y esa herramienta; no se cambiaron las reglas de funcionamiento del
diagramador durante la revisión.

## Orden de corrección

1. Impedir recuperar permisos reutilizando invitaciones y cubrirlo con regresiones.
2. Añadir revocación explícita de membresías y administración de colaboradores.
3. Limitar OCR/importaciones y definir gestión de sesiones.
4. Preservar metadatos XMI y unificar importaciones transaccionales.
5. Reducir snapshots y consultas innecesarias, incorporar control de conflictos
   y separar los servicios hoy concentrados en las vistas.
