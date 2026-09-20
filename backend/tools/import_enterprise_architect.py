"""Importa un JSON del diagramador UML directamente en Enterprise Architect.

Uso en Windows con Enterprise Architect instalado:
    python import_enterprise_architect.py modelo.json C:\\modelos\\colegio.qeax

Requiere:
    pip install pywin32
"""
import json
import math
import os
import sys
from pathlib import Path

CONNECTOR_TYPES = {
    "ASSOCIATION": "Association",
    "AGGREGATION": "Aggregation",
    "COMPOSITION": "Aggregation",
    "INHERITANCE": "Generalization",
    "REALIZATION": "Realisation",
    "DEPENDENCY": "Dependency",
}

VISIBILITY = {
    "PUBLIC": "Public",
    "PRIVATE": "Private",
    "PROTECTED": "Protected",
    "PACKAGE": "Package",
}


def load_model(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as source:
        model = json.load(source)
    if not isinstance(model, dict) or not isinstance(model.get("classes"), list):
        raise ValueError("El JSON no contiene una lista 'classes' válida.")
    return model


def put_attribute(ea_class, attribute: dict) -> None:
    item = ea_class.Attributes.AddNew(attribute.get("name", "atributo"), attribute.get("data_type", "String"))
    item.Visibility = VISIBILITY.get(attribute.get("visibility", "PRIVATE"), "Private")
    item.IsStatic = bool(attribute.get("is_static", False))
    item.Update()


def put_method(ea_class, method: dict) -> None:
    item = ea_class.Methods.AddNew(method.get("name", "metodo"), method.get("return_type", "void"))
    item.Visibility = VISIBILITY.get(method.get("visibility", "PUBLIC"), "Public")
    item.IsStatic = bool(method.get("is_static", False))
    item.Update()
    for parameter in method.get("parameters") or []:
        if isinstance(parameter, dict):
            name = parameter.get("name", "param")
            type_name = parameter.get("type", "String")
        else:
            parts = str(parameter).split(":", 1)
            name = parts[0].strip() or "param"
            type_name = parts[1].strip() if len(parts) == 2 else "String"
        parameter_item = item.Parameters.AddNew(name, type_name)
        parameter_item.Update()
    item.Update()


def import_model(ea, model: dict) -> None:
    package_name = model.get("name") or "Diagrama UML"
    root_models = ea.Models
    package = root_models.AddNew(package_name, "Package")
    package.Update()
    diagram = package.Diagrams.AddNew(package_name, "Class")
    diagram.Update()

    classes_by_name = {}
    classes_by_id = {}
    for index, class_data in enumerate(model["classes"]):
        name = class_data.get("name") or "NuevaClase"
        class_type = {"INTERFACE": "Interface", "ENUM": "Enumeration"}.get(class_data.get("kind"), "Class")
        ea_class = package.Elements.AddNew(name, class_type)
        ea_class.Abstract = class_data.get("kind") == "ABSTRACT"
        ea_class.Update()
        for attribute in class_data.get("attributes") or []:
            put_attribute(ea_class, attribute)
        for method in class_data.get("methods") or []:
            put_method(ea_class, method)
        ea_class.Update()
        classes_by_name[name.strip().lower()] = ea_class
        if class_data.get("id") is not None:
            classes_by_id[str(class_data["id"])] = ea_class

        def finite_number(value, default):
            try:
                number = float(value)
                return number if math.isfinite(number) else default
            except (TypeError, ValueError):
                return default

        left = int(finite_number(class_data.get("pos_x"), 80 + (index % 4) * 300))
        top = int(finite_number(class_data.get("pos_y"), 80 + (index // 4) * 240))
        width = max(80, int(finite_number(class_data.get("width"), 220)))
        height = max(60, int(finite_number(class_data.get("height"), 140)))
        geometry = f"l={left};r={left + width};t={-top};b={-(top + height)};"
        diagram_object = diagram.DiagramObjects.AddNew(geometry, "")
        diagram_object.ElementID = ea_class.ElementID
        diagram_object.Update()

    package.Elements.Refresh()
    for relation in model.get("relations") or []:
        source = classes_by_id.get(str(relation.get("source")))
        target = classes_by_id.get(str(relation.get("target")))
        if source is None:
            source = classes_by_name.get(str(relation.get("from", "")).strip().lower())
        if target is None:
            target = classes_by_name.get(str(relation.get("to", "")).strip().lower())
        if source is None or target is None:
            continue
        connector_type = CONNECTOR_TYPES.get(relation.get("relation_type", "ASSOCIATION"), "Association")
        connector = source.Connectors.AddNew(relation.get("label", ""), connector_type)
        connector.SupplierID = target.ElementID
        connector.ClientEnd.Cardinality = relation.get("multiplicity_source", "1")
        connector.SupplierEnd.Cardinality = relation.get("multiplicity_target", "1")
        if relation.get("relation_type") == "COMPOSITION":
            connector.SupplierEnd.Aggregation = 2
        elif relation.get("relation_type") == "AGGREGATION":
            connector.SupplierEnd.Aggregation = 1
        connector.Update()
        connector.ClientEnd.Update()
        connector.SupplierEnd.Update()

    package.Elements.Refresh()
    diagram.DiagramObjects.Refresh()
    diagram.DiagramLinks.Refresh()
    diagram.Update()


def open_model(ea, project_path: str) -> None:
    if not os.path.exists(project_path) and not ea.CreateModel(0, project_path, 0):
        raise RuntimeError(f"Enterprise Architect no pudo crear el proyecto: {project_path}")
    if not ea.OpenFile(project_path):
        raise RuntimeError(f"Enterprise Architect no pudo abrir el proyecto: {project_path}")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    try:
        import win32com.client
    except ImportError as exc:
        raise SystemExit("Falta pywin32. En PowerShell ejecuta: py -m pip install --user pywin32") from exc

    json_path = Path(sys.argv[1]).resolve()
    project_path = str(Path(sys.argv[2]).resolve())
    model = load_model(json_path)
    ea = win32com.client.Dispatch("EA.Repository")
    try:
        open_model(ea, project_path)
        import_model(ea, model)
    finally:
        ea.CloseFile()
        ea.Exit()
    print(f"Importación completada: {project_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
