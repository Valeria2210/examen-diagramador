# Frontend del Diagramador UML (Fase 1) — React + Vite + React Flow

Editor visual de diagramas de clases UML: crear clases (arrastrables), atributos, métodos y
relaciones, todo conectado en tiempo real al backend Django de la Fase 1.

Ya fue probado de punta a punta contra el backend: crear diagrama → clases → atributos →
métodos → relación, todo persistiendo en la API. Los pasos de abajo lo levantan igual en
tu máquina.

## Requisitos

- Node.js 18+ (verificar con `node --version`; si no lo tenés, descargalo de nodejs.org)
- El backend de la Fase 1 corriendo en `http://127.0.0.1:8000` (ver el otro proyecto)

## Pasos para levantarlo

```bash
# 1. Entrar a la carpeta del frontend
cd uml_frontend

# 2. Instalar dependencias
npm install

# 3. Copiar variables de entorno (apunta al backend Django)
cp .env.example .env

# 4. Levantar el servidor de desarrollo
npm run dev
```

Va a quedar disponible en `http://localhost:5173/`. Abrilo en el navegador con el
backend Django ya corriendo (`python manage.py runserver`) en otra terminal.

## Qué podés hacer en el editor

- **+ Nuevo diagrama**: crea un proyecto y un diagrama nuevos (te pide los nombres).
- **+ Clase**: agrega una clase nueva al lienzo, en una posición aleatoria.
- **Arrastrar una clase**: mové el mouse sobre el título de la clase y arrastrala; la
  posición se guarda automáticamente en el backend al soltarla.
- **Dentro de cada clase**:
  - Cambiar el tipo (Clase / Abstracta / Interfaz / Enum) con el selector superior.
  - Editar el nombre haciendo clic en el título.
  - "+ atributo" / "+ método" para agregar filas; cada campo se guarda al salir de foco (blur).
  - El símbolo a la izquierda de cada fila es la visibilidad UML (+ público, - privado, # protegido, ~ paquete).
  - El botón "✕" borra la clase, el atributo o el método.
- **Crear una relación**: arrastrá desde el borde derecho de una clase hasta el borde
  izquierdo de otra (los "handles" son los puntitos en los costados). Se crea como
  Asociación 1↔1 por defecto.
- **Editar una relación**: hacé clic en la etiqueta que aparece sobre la línea (multiplicidades
  + tipo) para abrir el panel y cambiar el tipo (asociación, agregación, composición,
  herencia, realización, dependencia), las multiplicidades o la etiqueta.

## Variables de entorno

`VITE_API_URL` en el `.env` apunta a la API del backend. Por defecto:
```
VITE_API_URL=http://127.0.0.1:8000/api
```
Si tu backend corre en otro puerto o dirección, cambialo ahí.

## Siguientes pasos (fuera de este alcance inicial)

- Asistente IA (Claude) para crear/editar el diagrama por texto o voz, con function-calling
  sobre las mismas acciones que ya expone este editor.
- Reconocimiento de foto de pizarra.
- Importar/exportar XMI (Enterprise Architect).
- Edición colaborativa multiusuario en tiempo real (WebSockets / Django Channels).
- Build de producción (`npm run build`) y despliegue en S3 + CloudFront.
