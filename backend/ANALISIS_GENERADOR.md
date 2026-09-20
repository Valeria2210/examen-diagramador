# Estado del generador de backend

El alcance `completo` genera un backend Spring Boot 3 / Java 17 ejecutable en
local con un solo comando:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-backend.ps1
```

El ZIP incluye aplicación y PostgreSQL en Docker Compose, migración inicial
Flyway, entidades JPA, DTOs, MapStruct, servicios transaccionales, repositorios,
controladores paginados, validación, errores JSON, Actuator, CORS, OpenAPI,
Swagger, Postman y manifiesto SHA-256.

## Seguridad generada

- Registro, login, logout y usuario actual bajo `/api/auth`.
- Contraseñas BCrypt y tokens opacos aleatorios; solo se guarda SHA-256 del token.
- Tokens con vencimiento configurable y revocación al cerrar sesión.
- Roles `USER` y `ADMIN`; borrar recursos requiere `ADMIN`.
- Usuario administrador inicial definido únicamente por variables de entorno.
- Postman guarda automáticamente el token de registro o login en `access_token`.

## Base de datos e integración Flutter

PostgreSQL es obligatorio. Flyway crea el esquema y Hibernate usa
`ddl-auto: validate`, por lo que un desajuste detiene el arranque en lugar de
modificar tablas silenciosamente. Los listados devuelven páginas Spring
(`content`, `number`, `size`, `totalElements`, `totalPages`). Flutter debe enviar
`Authorization: Bearer <token>` y consumir `content` en los listados.

## Verificación actual

- 111 pruebas Django aprobadas (4 omitidas por depender de características
  exclusivas de PostgreSQL en la suite SQLite).
- Proyecto generado compilado en Docker con Maven/Java 17.
- Arranque real contra PostgreSQL 17 y migración Flyway aprobados.
- HTTP real aprobado: health, login, registro, roles, CRUD, paginación, CORS,
  logout/revocación, `401`, `403` y `204`.
- Frontend compilado y 8 pruebas Node aprobadas.
- Auditoría npm: 0 vulnerabilidades conocidas tras actualizar Vite 6.4.3.

## Límite que no puede inferirse del UML

El generador entrega infraestructura y CRUD completos, pero no inventa reglas de
negocio. Los métodos UML, permisos por propietario/tenant, pagos, notificaciones,
flujos específicos y políticas de acceso por entidad deben implementarse según
los requisitos del sistema. Un usuario autenticado puede consultar y modificar
los recursos CRUD; el borrado queda restringido al administrador.
