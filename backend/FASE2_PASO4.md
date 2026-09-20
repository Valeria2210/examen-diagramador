# Paso 4: entidades primero y documentación offline

En el frontend, abre el generador y selecciona «Paso 4 · Solo entidades»
(selección inicial). Valida el modelo, genera el ZIP y ejecuta `mvn compile`
con Java 17+ en la carpeta extraída. La compilación no necesita una base de datos.

El endpoint `POST /api/generador/generar-backend/` acepta
`alcance: "entidades" | "completo"`. Para conservar compatibilidad con los
clientes anteriores, su valor predeterminado es `completo`.
El modo entidades renderiza únicamente entidades JPA y Application, con el
POM y configuración necesarios para un proyecto Spring Boot real. Conserva las
relaciones y tipos de PK existentes; getters y setters explícitos sustituyen
`@Data`, sin añadir Lombok al procesador MapStruct.

El modo completo conserva las capas anteriores y construye el contrato desde
el IR preparado que consumen las plantillas. No consulta `/v3/api-docs`.
Escribe `docs/openapi.json`, `docs/postman_collection.json` y README. Mantiene
una copia de la colección en la raíz para clientes anteriores. Swagger controla
solo la dependencia de documentación interactiva; los archivos offline siempre
se incluyen en el modo completo.

Los schemas usan nombres de DTO, tipos de PK, límites de longitud y relaciones
con IDs. Los cuerpos omiten PK autogeneradas y relaciones de solo lectura;
las referencias opcionales empiezan en null y las colecciones en []. Postman
agrupa cinco operaciones por entidad y guarda la PK tras crear un recurso.
Para probar relaciones, usa IDs existentes. Repetir POST con campos únicos
requiere cambiar sus valores.

## Métricas y validación

La respuesta y `docs/metricas.json` incluyen entidades, archivos y líneas Java,
duración del renderizado (antes de comprimir), entidades por segundo,
validación del IR y cantidad de endpoints documentados. No se estima ahorro
humano ni cobertura. Cada nuevo ZIP informa compilación PENDIENTE: generar
código no ejecuta Maven en el servidor Django.

Ejemplo reproducible:

```powershell
python manage.py shell -c "exec(open('generador/demo_step4.py').read())"
cd artifacts/step4-entities
mvn compile
```

Pruebas: `python manage.py test generador`; frontend: `npm run build`.
Los casos cubren ZIP aislado, relaciones, PK numéricas/UUID/String, campos DTO,
ejemplos ISO, documentación sin Swagger, permisos y selección de alcance.

Verificación realizada el 16 de septiembre de 2026:

- 17 pruebas Django aprobadas con SQLite, sin errores en el system check.
- Build de producción del frontend aprobado (TypeScript y Vite).
- Ejemplo en `artifacts/step4-entities`: 4 entidades, 5 archivos Java, 178 líneas.
- Renderizado del ejemplo: 56,85 ms; 70,36 entidades por segundo.
- `mvn -B compile` con Docker Maven 3.9.9 y Temurin 17: BUILD SUCCESS.
  Compiló los 5 archivos, incluyendo relaciones y PK Long, Integer, UUID y String.
  Duración de Maven: 3 minutos y 1 segundo, incluyendo descarga de dependencias.
- No se ejecutaron CRUD contra PostgreSQL ni se importó la colección en Postman
  durante esta verificación; los contratos y cuerpos se verificaron en pruebas.

Referencias del formato: [OpenAPI 3.0.3](https://spec.openapis.org/oas/v3.0.3)
y [Postman Collection 2.1](https://schema.postman.com/json/collection/v2.1.0/docs/index.html).
