# Fase 2: empaquetado, entrega y conexión React

El diagramador genera Spring Boot desde un diagrama guardado en Django.
React selecciona únicamente diagramas del propietario, envía su ID a
`POST /api/generar-backend/`, muestra progreso y descarga el ZIP automáticamente.
Se conserva `/api/generador/generar-backend/` para clientes anteriores.
La descarga usa el cliente autenticado del API; nunca navega directamente a
una URL externa recibida. Si falla, conserva la generación para reintentar.
El botón de la barra abre el flujo con el diagrama actual; las operaciones de
guardado pendientes impiden abrirlo.

## Checklist de la fase 2

| Paso | Implementación | Evidencia |
| --- | --- | --- |
| IR | IRBuilder normaliza clases, tipos, PK y asociaciones | Tests de IR y validación |
| App Django | Generación, validación, historial y descarga autenticados | Tests de API, permisos y auditoría |
| Entity | Plantilla JPA y modo aislado | Maven Java 17 del paso 4 |
| Repository/Controller | JpaRepository y cinco operaciones CRUD | Maven y pruebas HTTP de CRUD simple |
| Configuración | POM, PostgreSQL, Compose y Application | Proyecto final empaquetado con Maven |
| CRUD simple | Creación, lectura, actualización y borrado antes de relaciones | simple_crud en verify_delivery_api.py |
| Service/DTO/Mapper | Transacciones, validaciones y MapStruct | Compilación y rollback HTTP |
| Relaciones | 1-N, N-1, 1-1, N-N y autorrelaciones | Tests de generación y pruebas HTTP |
| React | Loading, POST por ID y descarga automática | Build y cuatro pruebas de entrega |
| OpenAPI/Postman | Conversión offline desde IR, DTOs y Bearer token | Tests de contrato, autenticación y cuerpos |
| Entrega | ZIP verificado, FileResponse, SHA-256, caducidad e historial | Tests de manifest, integridad, expiración y limpieza |

## Alcance UML

El generador implementa un subconjunto de diagramas de clases de
[UML 2.5.1](https://www.omg.org/spec/UML/2.5.1): clases concretas, atributos
persistentes, PK y asociaciones, agregaciones y composiciones con multiplicidades
1, 0..1, *, 0..* y 1..*. El diagramador puede representar más elementos que los
que el generador convierte. Interfaces, clases abstractas, enumeraciones,
herencia, realización y dependencia se rechazan para esta estrategia JPA.
Los métodos UML no generan reglas de negocio ni implementaciones automáticas.
No se certifica conformidad completa con el metamodelo UML ni se convierte XMI
arbitrario directamente desde este endpoint. Las importaciones pasan antes por
el modelo del diagramador. La composición activa cascada y eliminación de
huérfanos cuando el modelo es compatible.

## Seguridad y ciclo de vida

- Token del diagramador y propiedad del proyecto obligatorios tanto en POST
  como en GET. Compartir un diagrama no permite generar o descargar su backend.
- Límite predeterminado de 10 solicitudes de generación/validación por minuto
  por usuario. Límites de 50 entidades, 200 atributos por clase y 500 relaciones.
  El throttle de DRF es una protección básica; para múltiples workers configura
  un cache compartido y límites adicionales en el proxy.
- Nombres UUID, comprobación de rutas y rechazo de enlaces. El directorio
  GENERADOR_TMP_DIR es privado: no debe servirse como MEDIA ni STATIC.
- Primero se construye y verifica un .zip.part y después se publica el ZIP.
  Un fallo limpia el parcial; no sobrescribe un ZIP ya existente.
- docs/manifest.json enumera hashes SHA-256 de los archivos generados (excluye
  al propio manifiesto). La respuesta incluye hash y tamaño del ZIP completo.
  Django comprueba el hash antes del streaming; React comprueba tamaño y hash
  antes de iniciar la descarga. Las respuestas ZIP usan private/no-store y nosniff.
- Caducidad predeterminada: 24 horas desde la generación. La URL identifica
  el archivo y requiere autenticación; no es una URL pública firmada de bucket.
  Se conserva la entrega local con FileResponse, sin dependencia de almacenamiento cloud.
- Django actualizado de 5.0.6 a 5.2.17 LTS, conforme a la
  [tabla de versiones soportadas](https://www.djangoproject.com/download/).
- El CRUD generado usa usuarios persistidos, contraseñas BCrypt, tokens Bearer
  revocables almacenados como hash y roles USER/ADMIN. OpenAPI, Swagger y Postman
  documentan registro, login, logout y usuario actual. En producción sigue siendo
  obligatorio usar HTTPS y secretos distintos a los ejemplos locales.

Programa diariamente el siguiente comando con el programador de tareas del
servidor. La caducidad bloquea la descarga aunque la limpieza todavía no haya corrido.

```powershell
python manage.py limpiar_generaciones --dry-run
python manage.py limpiar_generaciones
```

Elimina únicamente ZIP UUID expirados y ZIP huérfanos antiguos en el directorio
configurado, conserva ZIP activos, otros archivos e historial. No elimina carpetas
temporales antiguas ni .zip.part dejados por una caída del proceso: esos requieren
una política de mantenimiento adicional. El código limpia temporales en fallos normales.
Las generaciones anteriores a la nueva migración carecen de hash histórico;
la entrega las conserva hasta su caducidad y aplica las comprobaciones de ruta.

## Uso y métricas

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
```

Reinicia Django si lo ejecutabas con --noreload. La migración de metadatos ya se
aplicó a PostgreSQL durante esta tarea. Configura DEBUG=False, ALLOWED_HOSTS,
CORS_ALLOWED_ORIGINS y HTTPS para un despliegue fuera de desarrollo.
El servidor genera código y documentación offline: no compila ni ejecuta Java
durante el POST. Cada ZIP nuevo informa compilación PENDIENTE.

Las métricas distinguen renderizado antes del ZIP de duración total del servidor
incluyendo empaquetado/hash, pero anterior a persistir el registro. Se muestran
entidades/s, archivos, líneas Java, relaciones por tipo, tamaño y caducidad.
El flag descargado indica que el servidor abrió la entrega; no prueba que el
usuario guardó el archivo. La descarga requiere un contexto seguro del navegador
(HTTPS o localhost) para Web Crypto.

## Verificación realizada el 16 de septiembre de 2026

- 90 pruebas Django aprobadas contra PostgreSQL, sin omisiones.
- Migraciones coherentes y pip check sin conflictos de dependencias.
- Build TypeScript/Vite de producción aprobado.
- Cuatro pruebas Node de entrega aprobadas: POST por ID, origen de API controlado,
  integridad antes del clic, ZIP corrupto/incompleto y errores JSON recibidos como Blob.
- Ejemplo independiente artifacts/step67-delivery: 4 entidades, 4 relaciones,
  29 archivos Java, 967 líneas; renderizado 152,30 ms y 26,26 entidades/s.
- mvn package: BUILD SUCCESS con Java 17, compilando los 29 archivos.
- HTTP del ejemplo final aprobado: 401 sin clave o con clave incorrecta; CRUD
  autenticado; cuatro tipos de PK; 1-N, 1-1, N-N y autorrelación; 400/404/409;
  rollback; duplicados; conservación, vaciado y desvinculación.
- El paso 5 midió 5 sentencias SQL para listar 60 clientes con pedidos.
- No había navegador conectado. El clic visual de la aplicación completa y la
  importación manual en Postman no se verificaron; el flujo de descarga se probó
  con DOM simulado y los endpoints CRUD por HTTP real.

```powershell
python manage.py test
cd ../frontend
npm run test:delivery
npm run build
```

Para repetir la verificación configura `APP_ADMIN_USERNAME`,
`APP_ADMIN_PASSWORD` y `GENERATED_API_URL`, y ejecuta
`generador/verify_delivery_api.py` contra el backend generado.

## Generación del diagrama actual y claves primarias

El diálogo de React utiliza exclusivamente el ID del diagrama abierto en el lienzo.
El botón espera a que terminen los guardados y la API conserva la comprobación de
propiedad del proyecto. No se selecciona otro diagrama como alternativa.

La opción visible «Completar claves primarias faltantes» envía `completar_pk: true`
en generación y validación. Sin PK explícita, el IR reutiliza un único identificador
compatible llamado `id`, `idNombreClase` o `NombreClaseId`. Si no es inequívoco,
añade un identificador Long con nombre disponible. No infiere PK de claves foráneas,
no cambia el diagrama en PostgreSQL y no corrige múltiples PK explícitas. La respuesta
incluye `avisos` y el ZIP conserva el modelo de generación en `ir.json`.
Los clientes que no envían esta opción mantienen la validación estricta original.

Se verificaron 29 pruebas Django del generador, 5 de entrega del frontend y la
compilación del frontend. La generación HTTP de «escuela» devolvió 201; su descarga
autenticada devolvió 200 con tamaño y SHA-256 correctos. El ZIP contiene 6 entidades,
5 relaciones y 41 archivos Java; el proyecto extraído quedó en
`artifacts/escuela-6b3fc3a2-0d80-4f08-bfdd-10e4e16767d8`.
La compilación limpia `mvn -B -DskipTests clean compile` terminó con BUILD SUCCESS
para sus 41 archivos fuente usando Java 17. Esto valida compilación; no implica
una prueba de arranque ni de CRUD HTTP de este nuevo proyecto.

## Generación en un clic y autocorrección

«Generar backend» abre el estado del proceso e inicia automáticamente el backend
completo del diagrama actual: CRUD REST, PostgreSQL, Swagger y colección Postman.
El diálogo impide solicitudes duplicadas y permite reintentar cuando hay un error.

React envía `autocorregir: true`. Django adapta nombres Java inválidos, reservados,
demasiado largos o duplicados; mantiene las referencias entre clases mediante sus
IDs; completa PK faltantes; reconoce tipos SQL/Java equivalentes y multiplicidades
`n`, `m`, `0..n`, `1..n`; evita conflictos en campos de entidades y DTO. El proceso
conserva clases y relaciones y termina pasando por la validación estricta del IR.

Se mantienen como errores los tipos desconocidos, múltiples PK explícitas,
relaciones de herencia/realización/dependencia y elementos distintos de CLASS.
Resolverlos requiere una estrategia de persistencia o una decisión del modelo.
La generación proporciona CRUD; los métodos UML no definen por sí solos la lógica
de negocio. No se convierten estos errores en datos inventados.

El ZIP incluye `diagrama_original.json` con el modelo completo, `ir.json` con el
modelo utilizado y `docs/correcciones.json` con el informe. Ambos documentos están
incluidos en el manifiesto SHA-256. No se modifica el diagrama guardado.

Validación: 34 pruebas Django, 5 de entrega del frontend y compilación del frontend
aprobadas. El flujo HTTP de escuela devolvió 201/200 y conservó el modelo original;
se verificó cada hash del manifiesto. Sus 41 archivos Java compilaron con Java 17
y BUILD SUCCESS. El ejemplo quedó en `artifacts/escuela-autocorregida`.
