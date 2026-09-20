import math

from django.db.models import Q
from rest_framework import serializers
from .models import Project, Diagram, UMLClass, Attribute, Method, Relation


class ProjectResourceSerializer(serializers.ModelSerializer):
    """Keep resources in their original parent and scope writable references."""

    parent_field = None
    related_project_paths = {}

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request is not None:
            user = request.user
            projects = Project.objects.none()
            if user.is_authenticated:
                projects = Project.objects.filter(Q(owner=user) | Q(members__user=user)).distinct()
            for field_name, project_path in self.related_project_paths.items():
                field = fields[field_name]
                lookup = f"{project_path}__in" if project_path else "pk__in"
                field.queryset = field.queryset.filter(**{lookup: projects})
        return fields

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None and self.parent_field in attrs:
            if attrs[self.parent_field].pk != getattr(self.instance, f"{self.parent_field}_id"):
                raise serializers.ValidationError({
                    self.parent_field: "No se puede cambiar el contenedor de un recurso existente."
                })
        return attrs


class AttributeSerializer(ProjectResourceSerializer):
    parent_field = "uml_class"
    related_project_paths = {"uml_class": "diagram__project"}

    class Meta:
        model = Attribute
        fields = ["id", "uml_class", "name", "data_type", "visibility", "is_static", "order", "es_pk", "es_unico", "nullable", "longitud"]
        extra_kwargs = {"longitud": {"min_value": 1}}


class MethodSerializer(ProjectResourceSerializer):
    parent_field = "uml_class"
    related_project_paths = {"uml_class": "diagram__project"}

    def validate_parameters(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Los parámetros deben ser una lista de objetos con nombre y tipo.")
        for index, parameter in enumerate(value):
            if not isinstance(parameter, dict):
                raise serializers.ValidationError(f"El parámetro {index + 1} debe ser un objeto con name y type.")
            for key in ("name", "type"):
                text = parameter.get(key)
                if not isinstance(text, str) or not text.strip() or len(text) > 100:
                    raise serializers.ValidationError(
                        f"El campo {key} del parámetro {index + 1} debe ser un texto de entre 1 y 100 caracteres."
                    )
        return value

    class Meta:
        model = Method
        fields = ["id", "uml_class", "name", "return_type", "visibility", "parameters", "is_static", "order"]


class UMLClassSerializer(ProjectResourceSerializer):
    """Serializer completo: incluye atributos y métodos anidados (solo lectura anidada)."""
    parent_field = "diagram"
    related_project_paths = {"diagram": "project"}
    attributes = AttributeSerializer(many=True, read_only=True)
    methods = MethodSerializer(many=True, read_only=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        for field_name in ("pos_x", "pos_y", "width", "height"):
            if field_name not in attrs:
                continue
            value = attrs[field_name]
            if not math.isfinite(value):
                raise serializers.ValidationError({field_name: "El valor debe ser un número finito."})
            if field_name in ("width", "height") and value <= 0:
                raise serializers.ValidationError({field_name: "El tamaño debe ser mayor que cero."})

        if "name" in attrs:
            diagram = attrs.get("diagram") or self.instance.diagram
            normalized_name = " ".join(attrs["name"].split()).casefold()
            existing_classes = UMLClass.objects.filter(diagram=diagram)
            if self.instance is not None:
                existing_classes = existing_classes.exclude(pk=self.instance.pk)
            if any(" ".join(name.split()).casefold() == normalized_name
                   for name in existing_classes.values_list("name", flat=True)):
                raise serializers.ValidationError({"name": "Ya hay una clase con ese mismo nombre."})
        return attrs

    class Meta:
        model = UMLClass
        fields = ["id", "diagram", "name", "kind", "pos_x", "pos_y", "width", "height", "attributes", "methods"]


class RelationSerializer(ProjectResourceSerializer):
    parent_field = "diagram"
    related_project_paths = {
        "diagram": "project",
        "source": "diagram__project",
        "target": "diagram__project",
    }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        diagram = attrs.get("diagram") or self.instance.diagram
        errors = {}
        for field_name in ("source", "target"):
            endpoint = attrs.get(field_name) or getattr(self.instance, field_name, None)
            if endpoint is not None and endpoint.diagram_id != diagram.pk:
                errors[field_name] = "La clase debe pertenecer al mismo diagrama que la relación."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    class Meta:
        model = Relation
        fields = [
            "id", "diagram", "source", "target", "relation_type",
            "multiplicity_source", "multiplicity_target", "label",
            "nombre_campo_origen", "nombre_campo_destino",
        ]


class DiagramSerializer(ProjectResourceSerializer):
    parent_field = "project"
    related_project_paths = {"project": ""}
    access_role = serializers.SerializerMethodField()

    def get_access_role(self, diagram):
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return None
        user = request.user
        if diagram.project.owner_id == user.id:
            return "OWNER"
        membership = diagram.project.members.filter(user=user).only("role").first()
        return membership.role if membership else None

    class Meta:
        model = Diagram
        fields = ["id", "project", "name", "created_at", "updated_at", "access_role"]


class DiagramDetailSerializer(DiagramSerializer):
    """Diagrama completo con sus clases y relaciones, listo para pintar en el canvas."""
    classes = UMLClassSerializer(many=True, read_only=True)
    relations = RelationSerializer(many=True, read_only=True)

    class Meta:
        model = Diagram
        fields = ["id", "project", "name", "created_at", "updated_at", "access_role", "classes", "relations"]


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "name", "description", "owner", "created_at", "updated_at"]
        extra_kwargs = {"owner": {"required": False, "read_only": True}}
