import json
from urllib import error as urllib_error
from urllib import request as urllib_request
from xml.etree.ElementTree import ParseError as XmlParseError

from decouple import config
from rest_framework import serializers, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from .models import Project, ProjectMember, ProjectShare, Diagram, DiagramVersion, UMLClass, Attribute, Method, Relation
from .serializers import (
    ProjectSerializer, DiagramSerializer, DiagramDetailSerializer,
    UMLClassSerializer, AttributeSerializer, MethodSerializer, RelationSerializer,
)
from .xmi_export import diagram_to_xmi
from .xmi_import import parse_xmi_to_spec
from .image_import import image_to_spec, validate_image_bytes
from .uml_analysis import analyze_diagram
from .throttles import AuthThrottle, AIThrottle


def user_payload(user):
    return {"id": user.id, "username": user.username, "email": user.email}


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def register(request):
    username = serializers.CharField(max_length=150, validators=User._meta.get_field("username").validators).run_validation(request.data.get("username"))
    email = serializers.EmailField(allow_blank=True).run_validation(request.data.get("email", ""))
    password = serializers.CharField(trim_whitespace=False).run_validation(request.data.get("password"))
    try:
        validate_password(password, User(username=username, email=email))
    except DjangoValidationError as exc:
        raise ValidationError({"detail": " ".join(exc.messages)}) from exc
    if User.objects.filter(username__iexact=username).exists():
        return Response({"detail": "Ese nombre de usuario ya está registrado."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            user = User.objects.create_user(username=username, email=email, password=password)
            token = Token.objects.create(user=user)
    except IntegrityError as exc:
        raise ValidationError({"detail": "Ese nombre de usuario ya está registrado."}) from exc
    return Response({"token": token.key, "user": user_payload(user)}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def login(request):
    username = serializers.CharField(max_length=150).run_validation(request.data.get("username"))
    password = serializers.CharField(trim_whitespace=False).run_validation(request.data.get("password"))
    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response({"detail": "Usuario o contraseña incorrectos."}, status=status.HTTP_400_BAD_REQUEST)

    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": user_payload(user)})


@api_view(["POST"])
def logout(request):
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
def current_user(request):
    return Response(user_payload(request.user))


UML_DIAGRAM_TOOL = {
    "name": "create_uml_diagram",
    "description": "Crea un prototipo de diagrama de clases UML 2.5 a partir de una descripción funcional.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["classes", "relations"],
        "properties": {
            "classes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "kind", "attributes", "methods"],
                    "properties": {
                        "name": {"type": "string"},
                        "kind": {"type": "string", "enum": ["CLASS", "ABSTRACT", "INTERFACE", "ENUM"]},
                        "attributes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "type", "visibility"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {"type": "string"},
                                    "visibility": {"type": "string", "enum": ["PUBLIC", "PRIVATE", "PROTECTED", "PACKAGE"]},
                                },
                            },
                        },
                        "methods": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "returnType", "visibility", "parameters"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "returnType": {"type": "string"},
                                    "visibility": {"type": "string", "enum": ["PUBLIC", "PRIVATE", "PROTECTED", "PACKAGE"]},
                                    "parameters": {"type": "array", "items": {"type": "string"}},
                                },
                            },
                        },
                    },
                },
            },
            "relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["from", "to", "type", "sourceMultiplicity", "targetMultiplicity", "label"],
                    "properties": {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "type": {"type": "string", "enum": ["ASSOCIATION", "AGGREGATION", "COMPOSITION", "INHERITANCE", "REALIZATION", "DEPENDENCY"]},
                        "sourceMultiplicity": {"type": "string"},
                        "targetMultiplicity": {"type": "string"},
                        "label": {"type": "string"},
                    },
                },
            },
        },
    },
}


@api_view(["POST"])
@throttle_classes([AIThrottle])
def interpret_uml(request):
    """Interpreta texto o una transcripción usando Claude tool use, sin exponer la API key."""
    description = serializers.CharField(max_length=20000).run_validation(request.data.get("description"))
    if not description:
        return Response({"detail": "La descripción del diagrama está vacía."}, status=status.HTTP_400_BAD_REQUEST)

    api_key = config("ANTHROPIC_API_KEY", default="")
    if not api_key:
        return Response({"detail": "Falta ANTHROPIC_API_KEY en backend/.env."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    payload = {
        "model": config("ANTHROPIC_MODEL", default="claude-sonnet-4-6"),
        "max_tokens": 3000,
        "system": "Diseña modelos conceptuales UML 2.5+. Usa solo conceptos del negocio, sin clases técnicas. Usa la herramienta create_uml_diagram y devuelve siempre todas las clases, atributos, métodos y relaciones deducibles.",
        "tools": [UML_DIAGRAM_TOOL],
        "tool_choice": {"type": "tool", "name": "create_uml_diagram"},
        "messages": [{"role": "user", "content": description}],
    }
    api_request = urllib_request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(api_request, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:500]
        if "credit balance is too low" in details.lower():
            return Response(
                {"detail": "Claude no tiene créditos disponibles. Agrega saldo en Anthropic Plans & Billing para generar diagramas desde texto o voz."},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        return Response({"detail": f"Claude rechazó la solicitud ({exc.code}). {details}"}, status=status.HTTP_502_BAD_GATEWAY)
    except (urllib_error.URLError, TimeoutError, ValueError) as exc:
        return Response({"detail": f"No se pudo conectar con Claude: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)

    content = result.get("content", []) if isinstance(result, dict) else []
    tool_use = next((item for item in content if isinstance(item, dict) and item.get("type") == "tool_use" and item.get("name") == "create_uml_diagram"), None)
    if not tool_use or not isinstance(tool_use.get("input"), dict):
        return Response({"detail": "Claude no devolvió un diagrama estructurado."}, status=status.HTTP_502_BAD_GATEWAY)
    return Response(tool_use["input"])


@api_view(["POST"])
def import_xmi(request):
    """
    POST /api/ai/import-xmi/  (multipart, campo 'file')
    Lee un .xmi (propio o exportado desde Enterprise Architect: Project > Export Package to XMI...)
    y devuelve el mismo formato {classes, relations} que usa el asistente de IA, para
    mostrarlo como vista previa y pegarlo en el lienzo tras confirmar.
    """
    uploaded = request.FILES.get("file")
    if not uploaded:
        return Response({"detail": "No se recibió ningún archivo .xmi."}, status=status.HTTP_400_BAD_REQUEST)
    if uploaded.name.lower().endswith((".qea", ".qeax", ".eap", ".eapx")):
        return Response({"detail": "Los proyectos nativos .qea/.qeax/.eapx no son XMI. En Enterprise Architect exporta el paquete como XMI 2.1 y sube el archivo .xmi."}, status=status.HTTP_400_BAD_REQUEST)
    if not uploaded.name.lower().endswith((".xmi", ".xml", ".zip")):
        return Response({"detail": "El archivo debe tener extensión .xmi, .xml o .zip con XMI."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        spec = parse_xmi_to_spec(uploaded.read())
    except XmlParseError as exc:
        return Response({"detail": f"El archivo no es un XMI válido: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:  # noqa: BLE001 - queremos devolver cualquier error de parseo como 400 legible
        return Response({"detail": f"No se pudo interpretar el XMI: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

    if not spec.get("classes"):
        return Response(
            {"detail": "No se encontraron clases en el archivo. Verificá que sea un export de paquete UML (Class/Interface/Enumeration)."},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return Response(spec)


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by("-updated_at")
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return super().get_queryset().filter(
            Q(owner=self.request.user) | Q(members__user=self.request.user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.owner_id != self.request.user.id:
            raise PermissionDenied("Solo el propietario puede modificar el proyecto.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.owner_id != self.request.user.id:
            raise PermissionDenied("Solo el propietario puede eliminar el proyecto.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        project = self.get_object()
        if not can_share_project(request.user, project.id):
            raise PermissionDenied("No tienes permiso para compartir el proyecto.")
        role = str(request.data.get("role", ProjectShare.Role.VIEWER)).upper()
        if role not in ProjectShare.Role.values:
            raise ValidationError({"detail": "El permiso debe ser VIEWER, EDITOR, SHARER o ADMIN."})
        if not can_manage_project(request.user, project.id) and role not in ("VIEWER", "SHARER"):
            raise PermissionDenied("Solo el propietario o un administrador puede conceder edición o administración.")
        share = ProjectShare.objects.create(project=project, created_by=request.user, role=role)
        return Response({"token": str(share.token), "role": share.role, "project": project.id}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def shares(self, request, pk=None):
        project = self.get_object()
        if not can_share_project(request.user, project.id):
            raise PermissionDenied("No tienes permiso para consultar los enlaces.")
        shares = project.shares.order_by("-created_at")
        if not can_manage_project(request.user, project.id):
            shares = shares.filter(created_by=request.user)
        return Response([
            {"token": str(item.token), "role": item.role, "active": item.active, "created_at": item.created_at}
            for item in shares
        ])

    @action(detail=True, methods=["post"])
    def revoke_share(self, request, pk=None):
        project = self.get_object()
        if not can_share_project(request.user, project.id):
            raise PermissionDenied("No tienes permiso para revocar enlaces.")
        token = serializers.UUIDField().run_validation(request.data.get("token"))
        shares = project.shares.filter(token=token, active=True)
        if not can_manage_project(request.user, project.id):
            shares = shares.filter(created_by=request.user)
        share = shares.first()
        if share is None:
            return Response({"detail": "El enlace no existe o ya fue revocado."}, status=status.HTTP_404_NOT_FOUND)
        share.active = False
        share.save(update_fields=["active"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"])
    def members(self, request, pk=None):
        project = self.get_object()
        if request.method == "GET":
            if not can_manage_project(request.user, project.id):
                raise PermissionDenied("Solo el propietario o un administrador puede consultar colaboradores.")
            return Response([{"id": item.user_id, "username": item.user.username, "role": item.role} for item in project.members.select_related("user")])
        if not can_manage_project(request.user, project.id):
            raise PermissionDenied("Solo el propietario o un administrador puede administrar colaboradores.")
        username = str(request.data.get("username", "")).strip()
        role = str(request.data.get("role", ProjectMember.Role.VIEWER)).upper()
        user = User.objects.filter(username__iexact=username).first()
        if not user or user == project.owner:
            return Response({"detail": "Indica un usuario válido que no sea el propietario."}, status=status.HTTP_400_BAD_REQUEST)
        if role not in ProjectMember.Role.values:
            return Response({"detail": "El permiso debe ser VIEWER, EDITOR, SHARER o ADMIN."}, status=status.HTTP_400_BAD_REQUEST)
        member, _ = ProjectMember.objects.update_or_create(project=project, user=user, defaults={"role": role})
        return Response({"id": member.user_id, "username": member.user.username, "role": member.role})


@api_view(["POST"])
def accept_share(request, token):
    share = ProjectShare.objects.filter(token=token, active=True).select_related("project").first()
    if share is None:
        return Response({"detail": "El enlace no existe o fue revocado."}, status=status.HTTP_404_NOT_FOUND)
    # Re-check the issuer: a previously issued link must not bypass a demotion.
    if not can_share_project(share.created_by, share.project_id):
        raise PermissionDenied("La persona que creó el enlace ya no puede compartir este proyecto.")
    if share.role in ("EDITOR", "ADMIN") and not can_manage_project(share.created_by, share.project_id):
        raise PermissionDenied("La persona que creó el enlace ya no puede conceder ese permiso.")
    effective_role = "OWNER"
    if share.project.owner_id != request.user.id:
        current = ProjectMember.objects.filter(project=share.project, user=request.user).first()
        if current is None or (current.role == "VIEWER" and share.role != "VIEWER") or share.role == "ADMIN":
            ProjectMember.objects.update_or_create(project=share.project, user=request.user, defaults={"role": share.role})
            effective_role = share.role
        else:
            # EDITOR and SHARER are separate capabilities, not successive ranks.
            effective_role = current.role
    return Response({"project": share.project_id, "project_name": share.project.name, "role": effective_role})


def accessible_projects(user):
    return Project.objects.filter(Q(owner=user) | Q(members__user=user)).distinct()


def can_edit_project(user, project_id):
    return Project.objects.filter(
        Q(owner=user) | Q(members__user=user, members__role__in=[ProjectMember.Role.EDITOR, ProjectMember.Role.ADMIN]),
        id=project_id,
    ).exists()


def can_share_project(user, project_id):
    return Project.objects.filter(
        Q(owner=user) | Q(members__user=user, members__role__in=[ProjectMember.Role.SHARER, ProjectMember.Role.ADMIN]),
        id=project_id,
    ).exists()


def can_manage_project(user, project_id):
    return Project.objects.filter(
        Q(owner=user) | Q(members__user=user, members__role=ProjectMember.Role.ADMIN),
        id=project_id,
    ).exists()


def diagram_snapshot(diagram, request=None):
    diagram = Diagram.objects.select_related("project").prefetch_related(
        "classes__attributes", "classes__methods", "relations"
    ).get(pk=diagram.pk)
    return DiagramDetailSerializer(diagram, context={"request": request}).data


def lock_diagram(diagram_id):
    # A write obtains a row lock on PostgreSQL and a write reservation on SQLite.
    # It must precede reads of the snapshot/version number inside the transaction.
    if not Diagram.objects.filter(pk=diagram_id).update(updated_at=F("updated_at")):
        raise NotFound("El diagrama ya no existe.")
    return Diagram.objects.get(pk=diagram_id)


@transaction.atomic
def create_diagram_version(diagram, user, label="", *, automatic=False):
    diagram = lock_diagram(diagram.pk)
    next_number = (diagram.versions.order_by("-version_number").values_list("version_number", flat=True).first() or 0) + 1
    version = DiagramVersion.objects.create(
        diagram=diagram, version_number=next_number,
        snapshot=diagram_snapshot(diagram), created_by=user,
        label=label, is_automatic=automatic,
    )
    if automatic:
        stale_ids = list(diagram.versions.filter(is_automatic=True).values_list("id", flat=True)[max(1, settings.DIAGRAM_AUTO_VERSION_LIMIT):])
        DiagramVersion.objects.filter(id__in=stale_ids).delete()
    return version


def diagram_for_instance(instance):
    if isinstance(instance, Diagram):
        return instance
    if isinstance(instance, UMLClass):
        return instance.diagram
    if isinstance(instance, Attribute) or isinstance(instance, Method):
        return instance.uml_class.diagram
    return instance.diagram


class ProjectResourceAccessMixin:
    def has_edit_access(self, project_id):
        return can_edit_project(self.request.user, project_id)

    def require_edit_access(self, project_id):
        if not self.has_edit_access(project_id):
            raise PermissionDenied("El proyecto está compartido en modo lectura.")

    def project_id_for_instance(self, instance):
        if hasattr(instance, "project_id"):
            return instance.project_id
        if hasattr(instance, "diagram"):
            return instance.diagram.project_id
        return instance.uml_class.diagram.project_id

    def project_id_for_data(self, validated_data):
        if "project" in validated_data:
            return validated_data["project"].id
        if "diagram" in validated_data:
            return validated_data["diagram"].project_id
        return validated_data["uml_class"].diagram.project_id

    def perform_create(self, serializer):
        self.require_edit_access(self.project_id_for_data(serializer.validated_data))
        parent = serializer.validated_data.get("diagram") or serializer.validated_data["uml_class"].diagram
        with transaction.atomic():
            diagram = lock_diagram(parent.pk)
            fresh = self.get_serializer(data=self.request.data)
            fresh.is_valid(raise_exception=True)
            serializer.instance = fresh.save()
            diagram.save(update_fields=["updated_at"])
            create_diagram_version(diagram, self.request.user, "Cambio guardado", automatic=True)

    def perform_update(self, serializer):
        self.require_edit_access(self.project_id_for_instance(serializer.instance))
        diagram = diagram_for_instance(serializer.instance)
        with transaction.atomic():
            diagram = lock_diagram(diagram.pk)
            instance = type(serializer.instance).objects.filter(pk=serializer.instance.pk).first()
            if instance is None:
                raise NotFound("El elemento ya no existe.")
            fresh = self.get_serializer(instance, data=self.request.data, partial=serializer.partial)
            fresh.is_valid(raise_exception=True)
            serializer.instance = fresh.save()
            diagram.save(update_fields=["updated_at"])
            create_diagram_version(diagram, self.request.user, "Cambio guardado", automatic=True)

    def perform_destroy(self, instance):
        self.require_edit_access(self.project_id_for_instance(instance))
        diagram = diagram_for_instance(instance)
        with transaction.atomic():
            diagram = lock_diagram(diagram.pk)
            if isinstance(instance, Diagram):
                instance.delete()
                return
            create_diagram_version(diagram, self.request.user, "Antes de eliminar", automatic=True)
            instance.delete()
            diagram.save(update_fields=["updated_at"])
            create_diagram_version(diagram, self.request.user, "Elemento eliminado", automatic=True)


class DiagramViewSet(ProjectResourceAccessMixin, viewsets.ModelViewSet):
    queryset = Diagram.objects.all().order_by("-updated_at")
    serializer_class = DiagramSerializer

    def get_queryset(self):
        return super().get_queryset().filter(project__in=accessible_projects(self.request.user)).select_related("project").prefetch_related(
            "classes__attributes", "classes__methods", "relations"
        )

    def get_serializer_class(self):
        if self.action == "retrieve" or self.action == "full":
            return DiagramDetailSerializer
        return DiagramSerializer

    def perform_create(self, serializer):
        self.require_edit_access(serializer.validated_data["project"].id)
        with transaction.atomic():
            diagram = serializer.save()
            create_diagram_version(diagram, self.request.user, "Diagrama creado", automatic=True)

    @action(detail=True, methods=["get"])
    def full(self, request, pk=None):
        """
        GET /api/diagrams/{id}/full/
        Devuelve el diagrama completo (clases + atributos + métodos + relaciones).
        Este es el JSON que luego se usará como entrada del generador de backend (Fase 2).
        """
        diagram = self.get_object()
        serializer = self.get_serializer(diagram)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def analyze(self, request, pk=None):
        """Revisa la consistencia UML del diagrama activo."""
        return Response(analyze_diagram(self.get_object()))

    @action(detail=True, methods=["get", "post"])
    def versions(self, request, pk=None):
        diagram = self.get_object()
        if request.method == "POST":
            self.require_edit_access(diagram.project_id)
            label = serializers.CharField(max_length=150, allow_blank=True).run_validation(request.data.get("label", "Punto guardado"))
            version = create_diagram_version(diagram, request.user, label)
            return Response({"id": version.id, "version_number": version.version_number, "label": version.label, "created_at": version.created_at}, status=status.HTTP_201_CREATED)
        return Response([
            {"id": version.id, "version_number": version.version_number, "label": version.label, "created_at": version.created_at, "created_by": version.created_by.username if version.created_by else None}
            for version in diagram.versions.select_related("created_by").all()
        ])

    @action(detail=True, methods=["post"])
    def restore_version(self, request, pk=None):
        diagram = self.get_object()
        self.require_edit_access(diagram.project_id)
        version_id = serializers.IntegerField(min_value=1).run_validation(request.data.get("version_id"))
        version = diagram.versions.filter(pk=version_id).first()
        if version is None:
            return Response({"detail": "La versión no existe."}, status=status.HTTP_404_NOT_FOUND)
        with transaction.atomic():
            diagram = lock_diagram(diagram.pk)
            create_diagram_version(diagram, request.user, "Antes de restaurar")
            diagram.name = version.snapshot.get("name", diagram.name)
            UMLClass.objects.filter(diagram=diagram).delete()
            new_classes = {}
            for index, item in enumerate(version.snapshot.get("classes", [])):
                new_class = UMLClass.objects.create(
                    diagram=diagram,
                    name=item.get("name", f"Clase{index + 1}"),
                    kind=item.get("kind", "CLASS"),
                    pos_x=item.get("pos_x", 80 + (index % 4) * 300),
                    pos_y=item.get("pos_y", 80 + (index // 4) * 240),
                    width=item.get("width", 220),
                    height=item.get("height", 140),
                )
                new_classes[item.get("id")] = new_class
                for order, attribute in enumerate(item.get("attributes", [])):
                    Attribute.objects.create(uml_class=new_class, name=attribute.get("name", "atributo"), data_type=attribute.get("data_type", "String"), visibility=attribute.get("visibility", "PRIVATE"), is_static=attribute.get("is_static", False), order=order,
                        es_pk=attribute.get("es_pk", False), es_unico=attribute.get("es_unico", False), nullable=attribute.get("nullable", True), longitud=attribute.get("longitud"))
                for order, method in enumerate(item.get("methods", [])):
                    Method.objects.create(uml_class=new_class, name=method.get("name", "metodo"), return_type=method.get("return_type", "void"), visibility=method.get("visibility", "PUBLIC"), parameters=method.get("parameters", []), is_static=method.get("is_static", False), order=order)
            for relation in version.snapshot.get("relations", []):
                source = new_classes.get(relation.get("source"))
                target = new_classes.get(relation.get("target"))
                if source and target:
                    Relation.objects.create(diagram=diagram, source=source, target=target, relation_type=relation.get("relation_type", "ASSOCIATION"), multiplicity_source=relation.get("multiplicity_source", "1"), multiplicity_target=relation.get("multiplicity_target", "1"), label=relation.get("label", ""),
                        nombre_campo_origen=relation.get("nombre_campo_origen", ""), nombre_campo_destino=relation.get("nombre_campo_destino", ""))
            diagram.save(update_fields=["name", "updated_at"])
            restored = create_diagram_version(diagram, request.user, f"Restaurada versión {version.version_number}")
        return Response({"version_number": restored.version_number, "message": "Versión restaurada correctamente."})

    @action(detail=True, methods=["post"])
    def save_as(self, request, pk=None):
        """
        POST /api/diagrams/{id}/save_as/  body: { "name": "Nuevo nombre" }
        Duplica el diagrama actual (clases, atributos, métodos y relaciones) bajo un
        nombre nuevo, dentro del mismo proyecto. El diagrama original no se modifica.
        """
        source = self.get_object()
        self.require_edit_access(source.project_id)
        new_name = serializers.CharField(max_length=150, allow_blank=True).run_validation(request.data.get("name", "")) or f"{source.name[:142]} (copia)"
        return self._copy_diagram(source, request, new_name)

    @transaction.atomic
    def _copy_diagram(self, source, request, new_name):
        source = lock_diagram(source.pk)
        new_diagram = Diagram.objects.create(project=source.project, name=new_name)

        id_map = {}
        for uml_class in source.classes.all().prefetch_related("attributes", "methods"):
            new_class = UMLClass.objects.create(
                diagram=new_diagram,
                name=uml_class.name,
                kind=uml_class.kind,
                pos_x=uml_class.pos_x,
                pos_y=uml_class.pos_y,
                width=uml_class.width,
                height=uml_class.height,
            )
            id_map[uml_class.id] = new_class.id

            for attr in uml_class.attributes.all():
                Attribute.objects.create(
                    uml_class=new_class,
                    name=attr.name,
                    data_type=attr.data_type,
                    visibility=attr.visibility,
                    is_static=attr.is_static,
                    order=attr.order,
                    es_pk=attr.es_pk,
                    es_unico=attr.es_unico,
                    nullable=attr.nullable,
                    longitud=attr.longitud,
                )
            for method in uml_class.methods.all():
                Method.objects.create(
                    uml_class=new_class,
                    name=method.name,
                    return_type=method.return_type,
                    visibility=method.visibility,
                    parameters=method.parameters,
                    is_static=method.is_static,
                    order=method.order,
                )

        for rel in source.relations.all():
            Relation.objects.create(
                diagram=new_diagram,
                source_id=id_map[rel.source_id],
                target_id=id_map[rel.target_id],
                relation_type=rel.relation_type,
                multiplicity_source=rel.multiplicity_source,
                multiplicity_target=rel.multiplicity_target,
                label=rel.label,
                nombre_campo_origen=rel.nombre_campo_origen,
                nombre_campo_destino=rel.nombre_campo_destino,
            )

        create_diagram_version(new_diagram, request.user, "Diagrama copiado", automatic=True)
        serializer = DiagramDetailSerializer(new_diagram, context={"request": request})
        return Response(serializer.data, status=201)

    @action(detail=True, methods=["post"])
    def import_image(self, request, pk=None):
        """Detecta clases y relaciones UML de una imagen con OpenCV y Tesseract."""
        uploaded = request.FILES.get("file")
        self.require_edit_access(self.get_object().project_id)
        if not uploaded:
            return Response({"detail": "No se recibió ninguna imagen."}, status=status.HTTP_400_BAD_REQUEST)
        if not uploaded.content_type or not uploaded.content_type.startswith("image/"):
            return Response({"detail": "El archivo debe ser una imagen (PNG, JPG, WEBP o BMP)."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            image_bytes = uploaded.read()
            validate_image_bytes(image_bytes)
            return Response(image_to_spec(image_bytes))
        except (ValueError, RuntimeError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception as exc:  # noqa: BLE001 - devolvemos un error legible del OCR local
            return Response({"detail": f"No se pudo analizar la imagen: {exc}"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    @action(detail=True, methods=["post"])
    def import_xmi(self, request, pk=None):
        """Importa un XMI y crea sus clases, miembros y relaciones en el diagrama."""
        uploaded = request.FILES.get("file")
        self.require_edit_access(self.get_object().project_id)
        if not uploaded:
            return Response({"detail": "No se recibió ningún archivo XMI."}, status=status.HTTP_400_BAD_REQUEST)
        if not uploaded.name.lower().endswith((".xmi", ".xml", ".zip")):
            return Response({"detail": "El archivo debe tener extensión .xmi, .xml o .zip con XMI."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            spec = parse_xmi_to_spec(uploaded.read())
        except XmlParseError as exc:
            return Response({"detail": f"El archivo no es un XMI válido: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001 - convertir errores de formatos EA en respuesta legible
            return Response({"detail": f"No se pudo interpretar el XMI: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
        if not spec.get("classes"):
            return Response({"detail": "No se encontraron clases UML en el archivo."}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        diagram = self.get_object()
        with transaction.atomic():
            diagram = lock_diagram(diagram.pk)
            create_diagram_version(diagram, request.user, "Antes de importar XMI", automatic=True)
            def save_imported(serializer_class, data):
                serializer = serializer_class(data=data, context={"request": request})
                serializer.is_valid(raise_exception=True)
                return serializer.save()

            created_by_name = {}
            for index, class_data in enumerate(spec["classes"]):
                name = (class_data.get("name") or f"Clase{index + 1}").strip()
                uml_class = save_imported(UMLClassSerializer, dict(
                    diagram=diagram.pk,
                    name=name,
                    kind=class_data.get("kind", "CLASS"),
                    pos_x=80 + (index % 4) * 300,
                    pos_y=80 + (index // 4) * 240,
                ))
                created_by_name[name.casefold()] = uml_class
                for order, attribute in enumerate(class_data.get("attributes") or []):
                    save_imported(AttributeSerializer, dict(
                        uml_class=uml_class.pk,
                        name=attribute.get("name", "atributo"),
                        data_type=attribute.get("type", "String"),
                        visibility=attribute.get("visibility", "private").upper(),
                        is_static=attribute.get("is_static", False),
                        order=order,
                    ))
                for order, method in enumerate(class_data.get("methods") or []):
                    parameters = []
                    for raw_parameter in method.get("parameters") or []:
                        if isinstance(raw_parameter, dict):
                            parameters.append(raw_parameter)
                        elif ":" in str(raw_parameter):
                            name, data_type = str(raw_parameter).split(":", 1)
                            parameters.append({"type": data_type.strip(), "name": name.strip()})
                        else:
                            parts = str(raw_parameter).split(None, 1)
                            parameters.append({"type": parts[0] if parts else "String", "name": parts[1] if len(parts) > 1 else "param"})
                    save_imported(MethodSerializer, dict(
                        uml_class=uml_class.pk,
                        name=method.get("name", "metodo"),
                        return_type=method.get("returnType", "void"),
                        visibility=method.get("visibility", "public").upper(),
                        parameters=parameters,
                        is_static=method.get("is_static", False),
                        order=order,
                    ))

            for relation in spec.get("relations") or []:
                source = created_by_name.get(str(relation.get("from", "")).casefold())
                target = created_by_name.get(str(relation.get("to", "")).casefold())
                if not source or not target:
                    raise ValidationError({"detail": "Una relación del XMI referencia una clase inexistente."})
                save_imported(RelationSerializer, dict(
                    diagram=diagram.pk,
                    source=source.pk,
                    target=target.pk,
                    relation_type=relation.get("type", "ASSOCIATION").upper(),
                    multiplicity_source=relation.get("sourceMultiplicity", "1"),
                    multiplicity_target=relation.get("targetMultiplicity", "1"),
                    label=relation.get("label", ""),
                ))
            diagram.save(update_fields=["updated_at"])
            create_diagram_version(diagram, request.user, "XMI importado", automatic=True)

        return Response(DiagramDetailSerializer(diagram, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def export_xmi(self, request, pk=None):
        """
        GET /api/diagrams/{id}/export_xmi/
        Descarga el diagrama como archivo .xmi (XMI 2.1 / UML 2.x), importable en
        Enterprise Architect (Menú EA: Project > Import Package from XMI...).
        """
        diagram = self.get_object()
        xml_bytes = diagram_to_xmi(diagram)
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in diagram.name).strip() or "diagrama"
        response = HttpResponse(xml_bytes, content_type="application/xml")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}.xmi"'
        return response

    @action(detail=True, methods=["get"])
    def export_ea_json(self, request, pk=None):
        """Descarga el modelo completo para el importador nativo de Enterprise Architect."""
        diagram = self.get_object()
        serializer = DiagramDetailSerializer(diagram)
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in diagram.name).strip() or "diagrama"
        response = Response(serializer.data, content_type="application/json")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}_enterprise_architect.json"'
        return response

    @action(detail=True, methods=["get"])
    def export_qea(self, request, pk=None):
        """Alias legado: entrega XMI, no un proyecto nativo de Enterprise Architect.

        Un archivo .qea/.qeax no es un ZIP de XMI; es una base de datos creada por
        Enterprise Architect. Se conserva la ruta para clientes antiguos, pero la
        respuesta usa la extensión y el tipo reales para que pueda importarse en EA.
        """
        diagram = self.get_object()
        xml_bytes = diagram_to_xmi(diagram)

        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in diagram.name).strip() or "diagrama"
        response = HttpResponse(xml_bytes, content_type="application/xml")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}.xmi"'
        return response


class UMLClassViewSet(ProjectResourceAccessMixin, viewsets.ModelViewSet):
    queryset = UMLClass.objects.order_by("id").select_related("diagram__project").prefetch_related("attributes", "methods")
    serializer_class = UMLClassSerializer

    def get_queryset(self):
        queryset = super().get_queryset().filter(diagram__project__in=accessible_projects(self.request.user))
        diagram_id = self.request.query_params.get("diagram")
        if diagram_id:
            diagram_id = serializers.IntegerField(min_value=1).run_validation(diagram_id)
            queryset = queryset.filter(diagram_id=diagram_id)
        return queryset


class AttributeViewSet(ProjectResourceAccessMixin, viewsets.ModelViewSet):
    queryset = Attribute.objects.all()
    serializer_class = AttributeSerializer

    def get_queryset(self):
        queryset = super().get_queryset().filter(uml_class__diagram__project__in=accessible_projects(self.request.user))
        class_id = self.request.query_params.get("uml_class")
        if class_id:
            class_id = serializers.IntegerField(min_value=1).run_validation(class_id)
            queryset = queryset.filter(uml_class_id=class_id)
        return queryset


class MethodViewSet(ProjectResourceAccessMixin, viewsets.ModelViewSet):
    queryset = Method.objects.all()
    serializer_class = MethodSerializer

    def get_queryset(self):
        queryset = super().get_queryset().filter(uml_class__diagram__project__in=accessible_projects(self.request.user))
        class_id = self.request.query_params.get("uml_class")
        if class_id:
            class_id = serializers.IntegerField(min_value=1).run_validation(class_id)
            queryset = queryset.filter(uml_class_id=class_id)
        return queryset


class RelationViewSet(ProjectResourceAccessMixin, viewsets.ModelViewSet):
    queryset = Relation.objects.order_by("id")
    serializer_class = RelationSerializer

    def get_queryset(self):
        queryset = super().get_queryset().filter(diagram__project__in=accessible_projects(self.request.user))
        diagram_id = self.request.query_params.get("diagram")
        if diagram_id:
            diagram_id = serializers.IntegerField(min_value=1).run_validation(diagram_id)
            queryset = queryset.filter(diagram_id=diagram_id)
        return queryset
