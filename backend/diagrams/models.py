import uuid

from django.db import models
from django.contrib.auth.models import User


class Project(models.Model):
    """Proyecto que puede contener uno o varios diagramas."""
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="projects", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class ProjectMember(models.Model):
    class Role(models.TextChoices):
        VIEWER = "VIEWER", "Solo lectura"
        EDITOR = "EDITOR", "Puede editar"
        SHARER = "SHARER", "Puede compartir"
        ADMIN = "ADMIN", "Administrador"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="project_memberships")
    role = models.CharField(max_length=15, choices=Role.choices, default=Role.VIEWER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "user"], name="unique_project_member")]


class ProjectShare(models.Model):
    class Role(models.TextChoices):
        VIEWER = "VIEWER", "Solo lectura"
        EDITOR = "EDITOR", "Puede editar"
        SHARER = "SHARER", "Puede compartir"
        ADMIN = "ADMIN", "Administrador"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="shares")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_project_shares")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    role = models.CharField(max_length=15, choices=Role.choices, default=Role.VIEWER)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)



class DiagramVersion(models.Model):
    diagram = models.ForeignKey("Diagram", on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    snapshot = models.JSONField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="diagram_versions")
    label = models.CharField(max_length=150, blank=True, default="")
    is_automatic = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version_number"]
        constraints = [models.UniqueConstraint(fields=["diagram", "version_number"], name="unique_diagram_version")]


class Diagram(models.Model):
    """Un diagrama de clases dentro de un proyecto."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="diagrams")
    name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.project.name} / {self.name}"


class UMLClass(models.Model):
    """Un elemento del diagrama: clase, interfaz o enum."""

    class Kind(models.TextChoices):
        CLASS = "CLASS", "Clase"
        ABSTRACT = "ABSTRACT", "Clase abstracta"
        INTERFACE = "INTERFACE", "Interfaz"
        ENUM = "ENUM", "Enum"

    diagram = models.ForeignKey(Diagram, on_delete=models.CASCADE, related_name="classes")
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CLASS)
    # Posición en el lienzo, para que el frontend (React Flow / JointJS) pueda repintar el diagrama tal cual quedó
    pos_x = models.FloatField(default=0)
    pos_y = models.FloatField(default=0)
    # Tamaño del cuadro en el lienzo (se puede redimensionar arrastrando desde el frontend)
    width = models.FloatField(default=220)
    height = models.FloatField(default=140)

    def __str__(self):
        return self.name


class Attribute(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = "PUBLIC", "+"
        PRIVATE = "PRIVATE", "-"
        PROTECTED = "PROTECTED", "#"
        PACKAGE = "PACKAGE", "~"

    uml_class = models.ForeignKey(UMLClass, on_delete=models.CASCADE, related_name="attributes")
    name = models.CharField(max_length=100)
    data_type = models.CharField(max_length=100, default="String")
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.PRIVATE)
    is_static = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    es_pk = models.BooleanField(default=False)
    es_unico = models.BooleanField(default=False)
    nullable = models.BooleanField(default=True)
    longitud = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.name}: {self.data_type}"


class Method(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = "PUBLIC", "+"
        PRIVATE = "PRIVATE", "-"
        PROTECTED = "PROTECTED", "#"
        PACKAGE = "PACKAGE", "~"

    uml_class = models.ForeignKey(UMLClass, on_delete=models.CASCADE, related_name="methods")
    name = models.CharField(max_length=100)
    return_type = models.CharField(max_length=100, default="void")
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC)
    # Parámetros como lista simple: [{"name": "id", "type": "Long"}, ...]
    parameters = models.JSONField(default=list, blank=True)
    is_static = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.name}()"


class Relation(models.Model):
    class RelationType(models.TextChoices):
        ASSOCIATION = "ASSOCIATION", "Asociación"
        AGGREGATION = "AGGREGATION", "Agregación"
        COMPOSITION = "COMPOSITION", "Composición"
        INHERITANCE = "INHERITANCE", "Herencia"
        REALIZATION = "REALIZATION", "Realización"
        DEPENDENCY = "DEPENDENCY", "Dependencia"

    diagram = models.ForeignKey(Diagram, on_delete=models.CASCADE, related_name="relations")
    source = models.ForeignKey(UMLClass, on_delete=models.CASCADE, related_name="relations_from")
    target = models.ForeignKey(UMLClass, on_delete=models.CASCADE, related_name="relations_to")
    relation_type = models.CharField(max_length=20, choices=RelationType.choices, default=RelationType.ASSOCIATION)
    multiplicity_source = models.CharField(max_length=20, blank=True, default="1")
    multiplicity_target = models.CharField(max_length=20, blank=True, default="1")
    label = models.CharField(max_length=100, blank=True, default="")
    nombre_campo_origen = models.CharField(max_length=100, blank=True, default="")
    nombre_campo_destino = models.CharField(max_length=100, blank=True, default="")

    def __str__(self):
        return f"{self.source.name} -> {self.target.name} ({self.relation_type})"
