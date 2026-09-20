# Fase 2: pasos 1 y 2

**Actualización:** el paso 3 está implementado. Las nuevas generaciones incluyen
el proyecto Spring Boot ejecutable; consulta [FASE2_PASO3.md](FASE2_PASO3.md).
La descripción de ZIP de IR que sigue documenta el alcance original del paso 2.

El paso 1 ahora incluye los metadatos de persistencia, el constructor de IR y su
validador. El paso 2 valida solicitudes, registra las generaciones en PostgreSQL,
empaqueta el IR y permite descargarlo mediante una petición autenticada.

**El ZIP contiene `ir.json`, `opciones.json` y `README.md`. Todavía no contiene
un backend Java ejecutable.** Las plantillas de las capas Spring Boot corresponden
al paso 3 del documento de referencia. La API devuelve `estado=IR_VALIDADO` y
`backend_ejecutable=false` para expresar este alcance.

## Desde el diagramador

1. En cada clase, agrega un atributo `id` de tipo `Long` y marca **PK**, o marca
   tu clave existente. Debe existir exactamente una PK por clase.
2. Los atributos permiten configurar **Único**, **Nulo** y **Longitud**.
3. Las relaciones permiten nombrar el campo en origen y destino. Vacíos reciben
   nombres derivados de las clases; si colisionan, se debe asignar un nombre explícito.
4. Abre **Backend · Fase 2**, elige el diagrama y pulsa **Validar modelo** para
   inspeccionar el IR. Pulsa **Preparar ZIP · Paso 2** y después **Descargar ZIP validado**.

La generación y descarga requieren ser propietario del proyecto. Los colaboradores
mantienen sus permisos de consulta y edición existentes, pero no pueden generar
ni descargar los archivos del propietario. La descarga usa `Authorization: Token`;
abrir directamente la URL en otra pestaña no envía ese encabezado.

## Postman

Base: `http://127.0.0.1:8000/api/generador/`.
Importa `postman_fase2_collection.json` y configura `token` y `diagrama_id`.
Obtén el token con el login existente `/api/auth/login/`.

| Método | Ruta | Resultado |
|---|---|---|
| POST | `validar/` | 200 y el IR, sin crear archivos ni registros |
| POST | `generar-backend/` | 201, ID, entidades y URL autenticada del ZIP |
| GET | `descargar/<nombre>.zip/` | 200, archivo ZIP del propietario |
| GET | `historial/` | Últimas 50 generaciones del usuario |

Solicitud de preparación:

```json
{"diagrama_id": 1, "incluir_swagger": true, "incluir_docker": true}
```

Swagger y Docker son opciones guardadas para las plantillas del paso 3.

Errores: 400 para solicitud inválida, diagrama vacío, tipos desconocidos, PK
ausente o múltiple, campos duplicados, relaciones inválidas o exceso de entidades;
401 sin token; 404 para diagrama/ZIP ajeno o inexistente; 500 con mensaje genérico
para fallos internos y detalles en el log del servidor.

## Tipos y relaciones admitidos

Tipos: String/texto/texto_largo, Integer/int/numero_entero, Long/numero_largo,
BigDecimal/numero_decimal, Double, Float, LocalDate/fecha,
LocalDateTime/fecha_hora, Boolean/booleano y UUID.
PK: Long, Integer, UUID o String. Las PK numéricas y UUID se marcan autogeneradas;
String requiere un valor suministrado. Las PK se normalizan como no nulas en el IR.
No se infieren PK de diagramas antiguos: deben marcarse explícitamente.

Asociación, agregación y composición se representan por su cardinalidad JPA
(OneToOne, OneToMany, ManyToOne o ManyToMany); aún no se definen políticas de
cascade ni orphan removal. Multiplicidades admitidas: 1, 0..1, *, 0..*, 1..*.
Herencia, realización, dependencia, clases abstractas, interfaces, enums y
atributos static se rechazan expresamente hasta contar con una estrategia de generación.
Los métodos UML siguen disponibles en el modelo original; este IR prepara
persistencia y no inventa implementaciones de lógica de negocio.

Los campos nuevos se conservan al copiar y restaurar versiones. Las versiones
anteriores a la migración recuperan valores predeterminados cuando no incluyen metadatos.

## Configuración y comprobaciones

`GENERADOR_TMP_DIR` usa por defecto `backend/generados`.
`GENERADOR_MAX_ENTIDADES` usa por defecto 50. Ambos admiten configuración en `.env`.
Los nombres de ZIP son UUID independientes por solicitud. Las rutas se validan
por componentes resueltos y se comprueba el registro y su usuario antes de abrir
el archivo. Un fallo al registrar elimina el ZIP recién creado.

Las migraciones `diagrams/0006` y `generador/0001` se aplicaron a PostgreSQL.
Para iniciarlo desde la raíz:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File backend/start-local.ps1
```

Pruebas desde la raíz, con el entorno instalado:

```powershell
$env:DEBUG='True'
$env:DB_ENGINE='postgres'
.\.venv\Scripts\python.exe backend/manage.py test generador diagrams.test_access_history diagrams.test_validation --noinput
```

Las pruebas usan una base `test_<DB_NAME>` separada y requieren permiso de creación
de base de datos. La limpieza programada de ZIP antiguos queda para el paso 6;
en este paso los archivos permanecen disponibles mientras existan.
