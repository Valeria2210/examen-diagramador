# Revisión del examen — 18/09/2026

El flujo principal funciona: React compila, Django pasa sus pruebas y un backend Spring Boot recién generado compila y ejecuta su CRUD contra PostgreSQL. Sin embargo, la generación no preserva todas las reglas del modelo y tiene casos que producen Java inválido. No se modificó el código funcional ni los datos de los diagramas.

## Verificaciones ejecutadas

| Verificación | Resultado |
|---|---|
| Frontend `npm run build` | Correcto: TypeScript y Vite |
| `npm run test:export` | 3/3 correctas |
| `npm run test:delivery` | 5/5 correctas |
| Django `manage.py check` | Sin incidencias |
| `makemigrations --check --dry-run` | Sin cambios pendientes de crear |
| Django con SQLite temporal | 95 correctas, 4 omitidas por falta de bloqueo de filas |
| Django con PostgreSQL temporal | 99/99 correctas, sin omisiones |
| PostgreSQL configurado en el proyecto | Todas las migraciones aplicadas |
| Generación nueva del ejemplo de ventas | ZIP generado y compilación Maven `BUILD SUCCESS` |
| Ejecución del ejemplo generado | Arranque correcto de Spring Boot 3.5.16, Java 17 y PostgreSQL 17 |
| Pruebas HTTP del ejemplo generado | CRUD, PK Long/Integer/UUID/String, 1-N, 1-1, N-N, autorrelación, validaciones, errores 404/409, rollback y OpenAPI correctos |
| API key | Petición sin clave rechazada con 401 |

Las pruebas se ejecutaron con `DEBUG` válido. Los errores iniciales `spawn EPERM` y de acceso a temporales se resolvieron ejecutando fuera del aislamiento: no son fallos del código.

## Diagramas reales de PostgreSQL

Se leyeron sin modificarlos y se generaron copias con autocorrección activada en `backend/audit_output/`.

| ID | Nombre | Clases | Relaciones | Generación |
|---|---|---:|---:|---|
| 1 | mar | 2 | 1 | Correcta |
| 2 | mar (copia) | 18 | 4 | Rechazada: `Coche.Conductor` tiene tipo `[]` |
| 4 | jool | 2 | 3 | Correcta |
| 5 | jool (copia) | 2 | 1 | Correcta |
| 6 | escuela | 6 | 5 | Correcta |

Las cuatro copias generadas (IDs 1, 4, 5 y 6) también pasaron `mvn package -DskipTests` en Docker con código de salida 0. Los proyectos generados no contienen pruebas Java; esta verificación demuestra compilación y empaquetado, no cobertura de negocio.

Generar y compilar no demuestra que los datos de negocio sean correctos. La ejecución HTTP completa se hizo sobre el ejemplo reproducible de ventas.

## Errores y problemas confirmados

### 1. Alta: nombres de entidades aceptados que rompen la compilación

Ubicación: `backend/generador/services/ir_builder.py:7` y `backend/generador/templates_springboot/Service.java.j2:14`.

`ENTITY_RESERVED` no incluye todos los tipos importados por las plantillas. Una entidad llamada `Objects` pasa la validación y se empaqueta, pero `ObjectsService.java` importa tanto la entidad como `java.util.Objects`. Maven falla con `reference to Objects is ambiguous` y conflicto de imports. Se reprodujo con un proyecto nuevo en `backend/audit_output/nombre_objects/`.

Corrección sugerida: usar nombres completamente cualificados para los tipos auxiliares o validar sistemáticamente las colisiones de todas las plantillas. Añadir una regresión que compile este caso.

### 2. Alta: claves foráneas duplicadas e independientes en escuela

Ubicación: `backend/generador/services/ir_builder.py:103` y `backend/generador/services/code_generator.py:40`.

La copia generada de `escuela` contiene `Curso.idProfesor` como atributo escalar y `Curso.profesor` como relación. Su DTO expone simultáneamente `idProfesor` y `profesorId`; la entidad almacena columnas distintas `f_idprofesor` y `r_0_profesor`. El servicio solo resuelve la relación al recibir `profesorId`. El atributo `idProfesor` no tiene validación de existencia ni sincronización con la relación: ambos pueden representar profesores diferentes.

Esto se confirma inspeccionando `backend/audit_output/diagrama_6/src/main/java/com/generado/escuela/entidades/Curso.java` y `dto/CursoDTO.java`. Si el atributo representa la FK de negocio, el contrato actual genera datos inconsistentes.

Corrección sugerida: detectar y advertir las posibles FK escalares duplicadas, y permitir asociarlas explícitamente a una relación. Evitar inferir automáticamente una equivalencia cuando sea ambigua.

### 3. Media: se pierden las restricciones mínimas de multiplicidad

Ubicación: `backend/generador/services/ir_builder.py:23`, `:148` y `backend/generador/templates_springboot/Entity.java.j2:28`.

`1` y `0..1` se convierten al mismo booleano; lo mismo ocurre con `*`, `0..*` y `1..*`. El IR no conserva obligatoriedad ni mínimos. Las referencias se generan sin `optional=false`, sin `nullable=false` en la FK y sin validación obligatoria en el DTO.

Reproducción HTTP: el ejemplo representa Cliente 1 → Pedido *, pero `POST /api/pedidos` con `{"total":1}` responde 201 y devuelve `clienteId:null`. El README generado reconoce esta limitación: es una capacidad pendiente de fidelidad UML, no un fallo de arranque.

Corrección sugerida: conservar ambos límites en el IR y traducir los requisitos aplicables a validaciones y restricciones de base de datos.

### 4. Media: XMI pierde la configuración necesaria para generar el backend

Ubicación: `backend/diagrams/xmi_export.py:103`, `backend/diagrams/xmi_import.py:192` y `backend/diagrams/views.py:678`.

El ciclo de exportación/importación conserva nombre, tipo, visibilidad y static de los atributos, pero no `es_pk`, `es_unico`, `nullable` ni `longitud`. También omite los nombres personalizados de campo de relación. Al volver a importar, esos datos toman sus valores predeterminados. Esto puede cambiar la PK y las restricciones del backend que se genere después.

Se comprobó con la exportación de los diagramas guardados 5 y 6: los atributos resultantes del parser no incluyen esos metadatos.

Corrección sugerida: incluir extensiones XMI para persistencia y nombres de relación, y restaurarlas en el parser y en el endpoint. Probar el ciclo completo de ida y vuelta.

### 5. Media: TEXT se convierte en un String de longitud predeterminada

Ubicación: `backend/generador/services/type_mapping.py:5`, `backend/generador/services/ir_builder.py:106` y `backend/generador/templates_springboot/Entity.java.j2:27`.

El alias SQL `TEXT` se acepta como `String`, pero `texto_largo` solo se activa si el texto original es exactamente `texto_largo`. Por eso `Curso.descripcion`, cuyo tipo original es `TEXT`, se genera sin `columnDefinition="text"` ni longitud explícita. No conserva la intención de texto largo; textos que excedan la longitud SQL predeterminada pueden ser rechazados.

Corrección sugerida: preservar la semántica de `TEXT` al mapearlo y validar coherentemente la longitud en el DTO.

### 6. Media: el SQLite incluido no está actualizado

Ubicación: `backend/db.sqlite3`.

`showmigrations` muestra pendientes `diagrams.0005`, `diagrams.0006` y las migraciones de `generador`. Consultar clases con sus atributos falla con `OperationalError: no such column: diagrams_attribute.es_pk`.

Esto afecta al modo de prueba `DB_ENGINE=sqlite` anunciado en el README. PostgreSQL actual sí está actualizado. No se aplicaron migraciones a las bases existentes durante esta revisión.

Corrección sugerida: ejecutar `manage.py migrate` cuando se vaya a usar SQLite o dejar de distribuir una copia desactualizada.

### 7. Configuración local: DEBUG=release impide iniciar Django directamente

Ubicación: `backend/backend/settings.py:7`.

La variable global de esta máquina tiene `DEBUG=release`. `python-decouple` la rechaza y Django falla antes de ejecutar comandos. `backend/start-local.ps1` ya contempla el problema y establece `DEBUG=True`. Los comandos directos necesitan un valor booleano válido.

Es un problema del entorno local, no una prueba de que Django esté roto. Solución: corregir la variable global o establecerla explícitamente en el proceso.

### 8. Datos del diagrama: tipo [] no soportado

En `mar (copia)` (ID 2), `Coche.Conductor` tiene `data_type='[]'`. El generador lo rechaza correctamente con `TipoNoSoportadoError`. La autocorrección no puede inferir qué elementos contiene esa colección.

Corrección sugerida: definir un tipo soportado o modelar una relación con Conductor según la intención del diagrama. No sustituirlo automáticamente por String.

## Limitaciones que conviene distinguir de errores

- Solo se generan clases `CLASS`; abstractas, interfaces y enums se rechazan expresamente.
- Herencia, realización y dependencia no tienen estrategia de persistencia implementada.
- Los métodos UML no se convierten en lógica de negocio. El resultado es un CRUD de persistencia.
- Las relaciones inversas son de solo lectura, documentadas en README y OpenAPI. Se confirmó que escribir `pedidosIds` en Cliente no modifica Pedido; hay que escribir `clienteId` en Pedido.
- Las PK numéricas y UUID se autogeneran; el modelo no ofrece una opción para PK numéricas asignadas por el usuario.
- El generador devuelve `backend_ejecutable=true` por el alcance completo, aunque la compilación queda `PENDIENTE`. No ejecuta Maven en cada generación. El caso Objects demuestra por qué conviene separar 'código generado' de 'compilación verificada'.
- Los listados generados usan `findAll()` sin paginación. Para volúmenes grandes pueden cargar demasiados registros y relaciones.
- La importación de imagen crea clases, miembros y relaciones en peticiones separadas desde React; si una petición intermedia falla, quedan datos parcialmente importados. Conviene un endpoint transaccional para confirmar el conjunto.
- El README del diagramador conserva instrucciones antiguas que dicen `AllowAny` y autenticación pendiente, aunque el código exige autenticación Token. También usa un nombre de carpeta distinto. Actualizarlo evita confundir las pruebas manuales.

No se hicieron llamadas de pago a Anthropic ni pruebas manuales de cámara, reconocimiento de voz o Enterprise Architect. No se verificó visualmente el editor en navegador. Las pruebas automatizadas no permiten certificar esas integraciones completas.

## Evidencias reproducibles

- `backend/audit_generate.py`: genera los casos de compilación y las copias de diagramas reales sin modificar la base.
- `backend/audit_runtime.py`: reproduce las limitaciones de relación y comprueba el 401 sin API key; necesita el ejemplo temporal de ventas en el puerto 58089.
- `backend/audit_tests.log`: suite con SQLite.
- `backend/audit_postgres_tests.log`: suite con PostgreSQL.
- `backend/audit_generation.log`: resultados de generación de los diagramas guardados.
- `backend/audit_output/`: ZIP y proyectos usados para la revisión.

Prioridad recomendada: corregir colisiones de nombres Java y duplicación de FK; después conservar metadatos XMI, semántica TEXT y restricciones de multiplicidad.
