# Preparación para producción en AWS

Se prepara el **diagramador React + Django**, que genera proyectos Spring Boot. Los Spring Boot descargados son aplicaciones independientes: este despliegue no los ejecuta ni publica automáticamente. No se han creado recursos AWS ni realizado despliegues.

## Arquitectura preparada

Una instancia EC2 con Docker Compose, PostgreSQL externo (por ejemplo RDS), Caddy como entrada HTTPS, React servido por Nginx y Django servido por Gunicorn. Solo el proxy publica puertos. Django, el frontend interno y la base no deben ser accesibles directamente desde Internet. El frontend usa `/api` en el mismo dominio.

Esta configuración usa volúmenes locales y está preparada para **una instancia**. Para varias instancias se necesita almacenamiento compartido privado para ZIP y una caché compartida como Redis; la caché de archivos actual comparte límites entre procesos del mismo servidor, pero no garantiza límites atómicos bajo concurrencia. No hay escalado automático preparado.

## Antes de arrancar

1. Definir una EC2, un dominio con DNS apuntando al servidor y un PostgreSQL accesible desde la EC2. Los puertos públicos son 80 y 443; restringir SSH a direcciones administrativas. RDS debe ser privado y permitir PostgreSQL únicamente desde la aplicación.
2. Instalar Docker y el complemento Compose en la instancia.
3. Copiar el proyecto excluyendo `.venv`, `node_modules`, `.env`, SQLite, `artifacts`, `generados` y `audit_output`. Los `.dockerignore` evitan que entren en las imágenes.
4. Copiar `.env.production.example` a `.env.production` en la raíz y completar los campos. No publicar ese archivo ni guardarlo en Git. En un entorno administrado, inyectar los secretos desde AWS Secrets Manager o el mecanismo de secretos elegido.
5. Generar una SECRET_KEY nueva con al menos 50 caracteres, por ejemplo `python -c "import secrets; print(secrets.token_urlsafe(64))"`. No reutilizar la clave local.
6. Usar el dominio real en SITE_DOMAIN, ALLOWED_HOSTS y CSRF_TRUSTED_ORIGINS. SITE_DOMAIN debe ser solo el nombre DNS, sin `https://` ni ruta. CORS puede quedar vacío porque el frontend y la API comparten origen.
7. Configurar DB_HOST, DB_NAME, DB_USER y DB_PASSWORD del PostgreSQL de producción. DB_SSLMODE=require usa cifrado; para verificar la identidad del servidor configurar verify-full y el certificado CA correspondiente mediante una configuración adicional de PostgreSQL. No usar las credenciales locales de ejemplo en producción.

El perfil de producción fuerza DEBUG=False, exige secretos y PostgreSQL, protege cookies y redirige a HTTPS. La confianza en X-Forwarded-Proto solo se activa en Compose porque Caddy sobrescribe ese header y el puerto de Django no está publicado. No exponer 8000 con esta opción habilitada.

## Preparar la versión y arrancar

Desde Windows se puede crear un paquete limpio, sin entornos virtuales, dependencias
locales, bases SQLite, artefactos de prueba ni archivos `.env`, ejecutando desde la raíz:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\package_aws.ps1
```

El resultado es `..\examen-aws.zip`. El archivo conserva los ejemplos de variables de
entorno, pero nunca incorpora las credenciales locales. Se debe copiar a la instancia,
descomprimir y crear allí `.env.production` a partir de `.env.production.example`.

Ejecutar desde la raíz en la EC2:

```sh
docker compose --env-file .env.production -f compose.production.yml config --quiet
docker compose --env-file .env.production -f compose.production.yml build
docker compose --env-file .env.production -f compose.production.yml run --rm backend python manage.py check --deploy
# Respaldar la base antes de migrar una base existente.
docker compose --env-file .env.production -f compose.production.yml run --rm backend python manage.py migrate --noinput
docker compose --env-file .env.production -f compose.production.yml run --rm backend python manage.py collectstatic --noinput
docker compose --env-file .env.production -f compose.production.yml up -d
```

`check --deploy` deja dos recomendaciones deliberadas: HSTS no cubre subdominios y no activa preload. No se conoce todavía si todos los subdominios usan HTTPS; no activar ambas opciones para ocultar avisos. HSTS empieza en una hora y puede ampliarse después de comprobar el dominio.

Caddy obtiene el certificado cuando el dominio resuelve correctamente y 80/443 están accesibles. La emisión real del certificado se debe verificar en AWS. Para crear un administrador, usar `docker compose --env-file .env.production -f compose.production.yml exec backend python manage.py createsuperuser`.

## Comprobar después del despliegue

- HTTPS válido, redirección HTTP a HTTPS y carga correcta del frontend al recargar una ruta.
- `/api/health/` devuelve 200 cuando PostgreSQL está disponible y 503 si falla.
- Registro, login, logout y rechazo de API sin autenticación.
- Crear proyecto, diagrama, clase, atributos y relación; recargar y confirmar persistencia.
- Compartir con VIEWER y EDITOR; comprobar que un lector no puede modificar.
- Generar un backend, descargar su ZIP con autenticación y verificar su integridad. Compilar el proyecto descargado con Java 17 y Maven.
- Abrir `/admin/` y confirmar que `/static/admin/css/base.css` carga.
- Confirmar que los volúmenes persisten después de reiniciar y que los registros no contienen secretos.

OCR incluye Tesseract español e inglés en la imagen. Voz e interpretación con IA requieren GEMINI_API_KEY y GEMINI_MODEL (por defecto gemini-3.5-flash-lite) configurados en .env.production. Cámara, voz del navegador y Enterprise Architect necesitan validación manual.

## Operación y recuperación

Activar respaldos de RDS y comprobar una restauración antes de usar datos importantes. Respaldar los volúmenes privados que deban conservarse. Mantener versiones identificables de las imágenes; para rollback usar la imagen anterior y comprobar compatibilidad con las migraciones. No ejecutar `down -v` contra producción.

Programar la limpieza de ZIP expirados y sesiones, por ejemplo diariamente desde cron en la EC2:

```sh
docker compose --env-file .env.production -f compose.production.yml exec -T backend python manage.py limpiar_generaciones
docker compose --env-file .env.production -f compose.production.yml exec -T backend python manage.py clearsessions
```

Configurar registros y alertas de disponibilidad en AWS. El proyecto no contiene aún infraestructura como código, monitorización o un flujo de publicación a ECR.

## Estado de las correcciones y pendientes

Corregidos durante la preparación: colisiones de entidades con tipos importados (incluido Objects) y preservación de TEXT como columna de texto largo. Se agregaron regresiones. Las imágenes de producción excluyen datos locales y secretos. Registro/login comparten un límite por IP (AUTH_RATE, 10/min en producción); IA tiene un límite por usuario (AI_RATE, 10/min). Una instancia usa un único proxy Caddy para identificar la IP: cambiar la topología requiere revisar NUM_PROXIES.

La auditoría inicial de dependencias Python encontró vulnerabilidades conocidas en DRF 3.15.2 y Pillow 11.0.0. Se actualizaron las versiones fijadas a DRF 3.17.2 y Pillow 12.3.0, también en `.venv` de esta máquina. Otros entornos necesitan reconstruir la imagen o reinstalar `requirements.txt` para aplicar esas versiones.

No se debe afirmar que todos los problemas funcionales están resueltos. Siguen pendientes:

- Resolver las FK escalares duplicadas con relaciones en `escuela`, por ejemplo `Curso.idProfesor` y `profesorId`.
- Conservar metadatos de persistencia y nombres de relaciones al exportar/importar XMI.
- Implementar restricciones mínimas de multiplicidad en el backend generado, si son requisito del examen.
- Corregir `Coche.Conductor` con tipo `[]` en `mar (copia)` para que ese diagrama pueda generarse.
- Actualizar SQLite si se va a usar localmente; producción usa PostgreSQL.
- Ajustar los límites de login e IA al tráfico real y complementar con controles en la infraestructura; los throttles de DRF no sustituyen protección contra ataques distribuidos.

La compilación correcta verifica el código Java, pero no estas reglas de negocio. Antes de una publicación definitiva se debe decidir el alcance exigido y resolver los puntos aplicables.

Referencias: [checklist de Django](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) y [proxy inverso de Caddy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).

## Verificación local reproducible

Después de construir `examen-production-backend` y `examen-production-frontend`, ejecutar `python deploy/verify_local.py`. El script crea contenedores, una red y un volumen temporales y los retira al terminar. Comprueba migraciones, archivos estáticos, pruebas de Django contra PostgreSQL, HTTPS con certificado interno de localhost, carga de React y rutas de SPA, autenticación, generación corregida de Objects y SHA-256 del ZIP. La excepción de validación de certificado solo existe en ese script para localhost; el despliegue real requiere un certificado público válido.

### Resultado de la verificación del 18/09/2026

- Ambas imágenes construidas correctamente; React pasó TypeScript, Vite y sus 8 pruebas en Linux.
- Django con las dependencias actualizadas: 109 pruebas correctas contra PostgreSQL temporal, sin omisiones. SQLite local pasó 105 y omitió 4 de concurrencia por limitaciones del motor.
- HTTPS local, SPA, archivos estáticos del admin, autenticación, logout, generación de ObjectsModelo y descarga del ZIP verificada por SHA-256: correctos.
- Compose y configuración de Caddy: válidos.
- `pip check`: sin conflictos. `npm audit --omit=dev`: sin vulnerabilidades reportadas.
- Auditoría final de `requirements-production.txt` con pip-audit: sin vulnerabilidades conocidas reportadas tras actualizar DRF y Pillow. Resultado completo en `backend/production_dependency_audit_final.log`.
- `check --deploy`: solo las dos recomendaciones de HSTS descritas arriba.

Los logs y artefactos locales de esa verificación no forman parte del paquete de despliegue. Los recursos de la integración fueron temporales y se eliminaron al terminar. Esto no verifica la infraestructura real de AWS, los certificados públicos, RDS ni backups; esos pasos requieren el entorno definitivo.
