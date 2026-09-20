# Paso 5: manejo de relaciones

Genera primero un CRUD sin asociaciones y verifica crear, buscar, actualizar y
eliminar. Después añade las relaciones desde el panel del diagrama; su resumen
JPA indica qué extremo guarda la FK. En el generador selecciona backend completo.
El modo del paso 4 sigue disponible para validar únicamente las entidades.

| Tipo del IR | Origen | Destino | Extremo escribible |
| --- | --- | --- | --- |
| OneToMany | OneToMany(mappedBy=campo_destino) | ManyToOne + JoinColumn | Destino |
| ManyToOne | ManyToOne + JoinColumn | OneToMany(mappedBy=campo_origen) | Origen |
| OneToOne | OneToOne + JoinColumn(unique=true) | OneToOne(mappedBy=campo_origen) | Origen |
| ManyToMany | ManyToMany + JoinTable | ManyToMany(mappedBy=campo_origen) | Origen |

Los nombres provienen de `nombre_campo_origen` y `nombre_campo_destino` del IR.
El builder conserva la normalización y los valores predeterminados del proyecto
cuando el diagrama no tiene un nombre explícito. El validador rechaza campos
vacíos en el IR, colisiones, duplicados (también con orientación invertida) y
autorrelaciones con campos iguales. Permite asociaciones distintas entre las
mismas clases, por ejemplo cliente y clienteFacturacion.

## DTO, mapper y servicio

Los DTOs exponen `{campo}Id` y `{campo}Ids` con el tipo real de la PK relacionada,
incluidos UUID, Integer y String. Las listas inversas se conservan como solo
lectura para compatibilidad con el paso 3. Los controllers devuelven DTOs.
MapStruct ignora asociaciones al crear y actualizar entidades; el servicio
consulta repositorios y devuelve 404 si una referencia no existe.

ManyToMany deduplica IDs, ejecuta `findAllById`, comprueba cada resultado y asigna
la colección después de validar todos los IDs. Un ID nulo responde 400. Un fallo
revierte también los cambios escalares gracias a la transacción.
PUT con referencia simple nula u omitida desvincula; una lista omitida se conserva
y `[]` la vacía. Las relaciones se escriben desde su propietario y se reflejan
en el extremo inverso en la siguiente lectura transaccional.

No hay cascadas de eliminación ni orphanRemoval automáticos: composición UML
no basta para inferir qué datos de negocio pueden borrarse. Una FK o restricción
de unicidad que impide el cambio responde 409.
El borrado usa una consulta JPQL por PK para evitar marcar como eliminada una
entidad todavía referenciada por objetos cargados en Hibernate. Antes limpia
solo las colecciones propietarias de tablas intermedias; todo ocurre en la
misma transacción, de modo que un conflicto revierte también esa limpieza.

## Carga de datos

Todas las asociaciones declaran LAZY explícitamente. Los repositorios cargan
relaciones simples con EntityGraph en findAll/findById y las colecciones usan
BatchSize de 50. No se unen varias listas en un mismo fetch, evitando el problema
de múltiples bags de Hibernate. El mapper se ejecuta dentro de la transacción
y open-in-view sigue deshabilitado. LAZY por sí solo no garantiza ausencia de N+1,
y un OneToOne inverso puede requerir consultas adicionales según el modelo.
Los listados actuales no tienen paginación; para diagramas grandes conviene
añadir endpoints paginados y evitar payloads de listas inversas extensas.

Las tablas intermedias usan `uml_rel_` más un hash estable de clases y campos:
20 caracteres, dentro del límite PostgreSQL. Para migrar una base de un proyecto
generado anteriormente, estos nuevos nombres requieren una migración explícita;
`ddl-auto=update` no mueve datos de las tablas intermedias antiguas.

## Ejemplo y verificación

```powershell
$env:DEBUG='True'
python manage.py shell -c "exec(open('generador/demo_step5.py').read())"
cd artifacts/step5-relations
mvn package
```

El ejemplo separado conserva step3-demo y step4-entities. Incluye Cliente/Pedido
(1-N), Cliente/Perfil (1-1), Pedido/Etiqueta (N-N) y Cliente.supervisor/subordinados
(autorrelación). PostgreSQL del ejemplo usa puerto 5434; la API de prueba usa 8085.

Para ejecutarlo sin Java instalado en Windows, desde la carpeta del ejemplo:

```powershell
$env:DB_PORT='5434'
docker compose -p fase5-relations up -d --wait
docker run --rm --network fase5-relations_default --env DB_URL=jdbc:postgresql://postgres:5432/ventasdemo --mount "type=bind,source=$PWD,target=/workspace" --mount type=volume,source=fase3-maven-cache,target=/root/.m2 --workdir /workspace maven:3.9.9-eclipse-temurin-17 mvn package
docker run -d --name fase5-relations-api --network fase5-relations_default -p 127.0.0.1:8085:8080 --env DB_URL=jdbc:postgresql://postgres:5432/ventasdemo --mount "type=bind,source=$PWD,target=/workspace,readonly" maven:3.9.9-eclipse-temurin-17 java -jar /workspace/target/ventasdemo-0.0.1-SNAPSHOT.jar
```

Si el contenedor del ejemplo ya existe, usa `docker start fase5-relations-api`.
Para recompilar su JAR en Windows, primero usa `docker stop fase5-relations-api`
para liberar el archivo. Para detener la base conservando datos usa
`docker compose -p fase5-relations stop` desde esa carpeta.
Ejecuta el siguiente script desde la carpeta backend:

```powershell
$env:GENERATED_API_URL='http://127.0.0.1:8085'
python generador/smoke_step5.py
```

La prueba HTTP crea y elimina datos propios y verifica primero CRUD simple,
luego relaciones válidas, referencias inexistentes, unicidad, rollback,
duplicados, conservación y vaciado de colecciones. La prueba Java del ejemplo
`RelationsBatchTest` crea 60 clientes con pedidos dentro de una transacción que
se revierte, mide sentencias SQL al listar DTOs y exige como máximo 10.
Los archivos de métricas distinguen renderizado de compilación; las métricas
del generador incluyen cantidad de relaciones por tipo.

Verificación del 16 de septiembre de 2026:

- 20 pruebas Django aprobadas con SQLite y build TypeScript/Vite aprobado.
- Maven compiló y empaquetó el backend completo con Java 17.
- Una prueba Spring Boot/Hibernate contra PostgreSQL aprobada, sin errores:
  60 clientes con pedidos, 5 sentencias SQL al convertir el listado a DTOs.
- Pruebas HTTP aprobadas: CRUD simple, cuatro tipos de PK, 1-N, 1-1, N-N,
  autorrelación, 400/404/409, rollback, dos IDs, duplicados, vaciado y desvinculación.
- Ejemplo final: 4 entidades, 4 relaciones, 27 archivos Java y 904 líneas.
  Renderizado: 86,24 ms; 46,38 entidades por segundo; 20 endpoints documentados.
- API de prueba disponible en http://127.0.0.1:8085/swagger-ui.html.

Referencias: [Spring Data JPA: EntityGraph](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
y [Hibernate 6.6: asociaciones y batch fetching](https://docs.hibernate.org/orm/6.6/userguide/html_single/).
