from __future__ import annotations

import re

from .models import Diagram


CLASS_NAME_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9_]*$")


def analyze_diagram(diagram: Diagram) -> dict:
    classes = list(diagram.classes.all().prefetch_related("attributes", "methods"))
    relations = list(diagram.relations.select_related("source", "target"))
    findings: list[dict] = []

    names: dict[str, list] = {}
    for uml_class in classes:
        normalized = " ".join(uml_class.name.split()).casefold()
        names.setdefault(normalized, []).append(uml_class)
        if not CLASS_NAME_PATTERN.fullmatch(uml_class.name.strip()):
            findings.append({
                "code": "INCONSISTENT_CLASS_NAME",
                "severity": "warning",
                "message": f"La clase '{uml_class.name}' no usa un nombre UML consistente.",
                "class_id": uml_class.id,
            })

        attribute_names: set[str] = set()
        for attribute in uml_class.attributes.all():
            attribute_key = " ".join(attribute.name.split()).casefold()
            if attribute_key in attribute_names:
                findings.append({
                    "code": "DUPLICATE_ATTRIBUTE",
                    "severity": "error",
                    "message": f"La clase '{uml_class.name}' tiene el atributo '{attribute.name}' repetido.",
                    "class_id": uml_class.id,
                    "attribute_id": attribute.id,
                })
            attribute_names.add(attribute_key)

    for normalized, duplicated in names.items():
        if len(duplicated) > 1:
            findings.append({
                "code": "DUPLICATE_CLASS",
                "severity": "error",
                "message": f"Hay {len(duplicated)} clases con el nombre '{duplicated[0].name}'.",
                "class_ids": [item.id for item in duplicated],
            })

    class_ids = {item.id for item in classes}
    for relation in relations:
        if relation.source_id not in class_ids or relation.target_id not in class_ids:
            findings.append({
                "code": "INVALID_RELATION",
                "severity": "error",
                "message": "La relación apunta a una clase que no existe en el diagrama.",
                "relation_id": relation.id,
            })
        if not relation.multiplicity_source.strip() or not relation.multiplicity_target.strip():
            findings.append({
                "code": "MISSING_MULTIPLICITY",
                "severity": "warning",
                "message": f"La relación entre '{relation.source.name}' y '{relation.target.name}' no tiene todas sus multiplicidades.",
                "relation_id": relation.id,
            })
        if relation.source_id == relation.target_id and relation.relation_type == "INHERITANCE":
            findings.append({
                "code": "INVALID_INHERITANCE",
                "severity": "error",
                "message": f"La clase '{relation.source.name}' no puede heredar de sí misma.",
                "relation_id": relation.id,
            })

    severity_order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda item: severity_order[item["severity"]])
    return {
        "diagram_id": diagram.id,
        "findings": findings,
        "summary": {
            "errors": sum(item["severity"] == "error" for item in findings),
            "warnings": sum(item["severity"] == "warning" for item in findings),
            "total": len(findings),
        },
    }
