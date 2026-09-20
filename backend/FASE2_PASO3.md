# Fase 2, paso 3: generar el backend Spring Boot

El endpoint existente `POST /api/generador/generar-backend/` ahora entrega un ZIP
con un proyecto Maven completo: entidades JPA, repositorios Spring Data, DTOs,
mappers MapStruct, servicios transaccionales, controladores REST y manejo global
de excepciones. Incluye configuración PostgreSQL, README, IR y colección Postman.
Swagger y Docker se incluyen según las opciones de la solicitud.

## Usarlo desde el diagramador

1. Guarda un diagrama con una PK marcada por clase. Se admiten Long, Integer,
   UUID y String; el nombre puede ser `codigoCliente` u otro nombre válido.
2. Abre **Backend · Fase 2**, selecciona el diagrama y valida el modelo.
3. Marca las opciones **Incluir Swagger** e **Incluir Docker**.
4. Pulsa **Generar backend Spring Boot** y descarga el ZIP.
5. Descomprime el archivo y sigue el README incluido.

La respuesta de generación devuelve `estado: SPRING_BOOT_GENERADO` y
`backend_ejecutable: true`: significa que incluye código y configuración para
construir y ejecutar el proyecto; el servidor Django no compila cada solicitud.
Las generaciones antiguas del paso 2 siguen conteniendo únicamente su IR.

## Ejecutar el proyecto descargado

Requiere Java 17 o superior y Maven 3.6.3 o superior. Desde su carpeta:

```powershell
docker compose up -d --wait
mvn clean verify
mvn spring-boot:run
```

La API está en `http://127.0.0.1:8080`. La base generada usa PostgreSQL 17 en
`localhost:5433`, usuario `app`, contraseña local `localdev` y nombre tomado del
proyecto. La base del diagramador permanece en 5432. No copia los datos del
diagramador: el sistema generado tiene su propio esquema y datos.

Sin Docker, crea una base PostgreSQL y configura las variables del proceso Spring:

```powershell
$env:DB_URL='jdbc:postgresql://localhost:5433/mi_base'
$env:DB_USER='mi_usuario'
$env:DB_PASSWORD='mi_clave'
$env:SERVER_PORT='8080'
mvn spring-boot:run
```

`DB_PORT` cambia el puerto publicado de Compose; si lo modificas, ajusta también
`DB_URL` en Spring. `ddl-auto=update` crea las tablas para desarrollo local.

## Probar relaciones en Postman

Importa `postman_collection.json` del ZIP. Tiene cinco solicitudes CRUD por
entidad y guarda la PK devuelta por POST como variable de colección.
La ruta se deriva del nombre de clase en minúsculas más `s`; el README enumera
las rutas exactas. Por ejemplo, Cliente → `/api/clientes`, Perfil → `/api/perfils`.

Para Cliente 1 → Pedido *, con campo destino `cliente`:

```http
POST /api/clientes
Content-Type: application/json

{"nombre":"Ana"}
```

Usa la PK devuelta en:

```http
POST /api/pedidos
Content-Type: application/json

{"total":12.50,"clienteId":1}
```

Los DTOs contienen IDs relacionados, sin entidades anidadas. Las colecciones
inversas se consultan desde el padre, pero se modifican desde el lado propietario.
OneToOne tiene ambas entidades y `mappedBy` inverso. ManyToMany tiene tabla de
unión por relación y lista de IDs escribible en origen. ManyToOne funciona aunque
el diagrama esté dibujado en sentido inverso. Las autorrelaciones generan ambos
extremos. Los repositorios y parámetros REST respetan el tipo real de la PK.

PUT carga y modifica la entidad existente; no sustituye su PK ni destruye sus
colecciones inversas. PUT sustituye campos escalares y referencias simples;
omitir o enviar null en una referencia simple la elimina. En una colección
propietaria, omitir el campo conserva el vínculo y enviar `[]` lo vacía.
Errores: 400 por validación, JSON/ID inválido o PK incompatible; 404 por registro
o ID relacionado inexistente; 409 por unicidad o dependencias que impidan borrar;
500 genérico con detalles registrados solo en el log.

Sin cascadas de borrado automáticas: desvincula o elimina dependientes primero.
Las multiplicidades se convierten en tipos JPA; las restricciones mínimas de
elementos y la lógica de negocio de métodos UML requieren una fase posterior.
Enums, interfaces, abstractas, herencia y dependencias se rechazan expresamente
según el validador actual. El CRUD generado es local y no incorpora autenticación
automática; Django sí exige Token y propiedad para generar/descargar.

El validador rechaza nombres que colisionen con tipos/anotaciones Java y campos
DTO de relaciones que colisionen con atributos. Límites tras normalizar: 50
caracteres para proyecto/clases/atributos y 45 para campos de relación, evitando
identificadores PostgreSQL truncados.

## Plantillas e infraestructura

`templates_springboot/` contiene las plantillas Jinja2. Se usa StrictUndefined para
detectar campos ausentes, UTF-8 y rutas verificadas. `file_writer.py` centraliza
la escritura y `zip_packager.py` empaqueta rutas relativas. Cada generación tiene
su carpeta temporal y un ZIP UUID independiente; la carpeta se elimina tanto
al finalizar como al fallar. Los errores internos no exponen detalles de plantillas.

Se generan getters/setters explícitos en lugar de Lombok para que MapStruct no
dependa del binding entre dos procesadores de anotaciones. El compilador Maven
configura el procesador MapStruct 1.6.3 y los mappers se inyectan como beans Spring.
Las entidades no usan `@Data`, evitando equals/toString recursivos en relaciones.
`texto_largo` usa una columna PostgreSQL `text`.

Versiones usadas: Spring Boot 3.5.16, Java 17, MapStruct 1.6.3, Springdoc 2.8.16
y PostgreSQL 17. Referencias: [requisitos Spring Boot](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
y [compatibilidad Springdoc](https://springdoc.org/v2/).

## Ejemplo y verificación

El ejemplo en `backend/artifacts/step3-demo` se genera sin modificar los diagramas
existentes. Tiene Cliente, Pedido, Perfil y Etiqueta; cuatro tipos de PK, fechas,
decimal, booleano y relaciones 1-N, 1-1, N-N y una autorrelación.

Verificación realizada: compilación Maven con `BUILD SUCCESS`, 48 pruebas Django
aprobadas contra PostgreSQL, compilación del frontend aprobada y prueba HTTP del
ejemplo aprobada con CRUD, relaciones, rollback y OpenAPI. La base de ejemplo
está en el servicio Compose `fase3-demo`; el JAR está levantado en el contenedor
`fase3-generated-api` y responde en http://127.0.0.1:8080.

En esta máquina se compiló/ejecutó con Java 17 y Maven dentro de Docker; no es
necesario instalar Java en Windows para usar el ejemplo que ya está levantado.
Para detener o reiniciar solo el JAR de ejemplo usa `docker stop fase3-generated-api`
o `docker start fase3-generated-api`. Para detener su base, desde la carpeta del
ejemplo usa `docker compose -p fase3-demo stop`.

También se verificó el servidor Django por HTTP con datos desechables:
POST devolvió 201, se registró la generación, el GET autenticado descargó el ZIP
con 200 y el historial marcó `descargado=true`. La prueba eliminó su diagrama,
registro y ZIP sin modificar los diagramas existentes.

Generación reproducible en una carpeta nueva (el script conserva la existente):

```powershell
$env:DEBUG='True'
$env:DB_ENGINE='postgres'
.\.venv\Scripts\python.exe backend/manage.py shell -c "import runpy; runpy.run_path('backend/generador/demo_step3.py', run_name='__main__')"
```

Prueba HTTP contra el ejemplo levantado:

```powershell
.\.venv\Scripts\python.exe backend/generador/smoke_generated.py
```

Esta prueba crea y elimina sus propios datos de ejemplo; verifica CRUD, relaciones,
tipos de PK, errores, rollback transaccional y OpenAPI. Para otra URL configura
`GENERATED_API_URL`. La colección Postman proviene directamente del IR; la
conversión automática de OpenAPI a Postman queda disponible para el paso 4.
