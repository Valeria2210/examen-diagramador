"""Importa un archivo XMI (propio o exportado desde Enterprise Architect) y lo convierte
al mismo formato de "spec" {classes, relations} que ya produce el asistente de IA
(ver AIAssistant.tsx -> AiDiagramSpec). Así, el resultado se puede pegar en el lienzo
reusando exactamente el mismo flujo de vista previa / confirmar que la foto o el texto.

Es tolerante a variaciones porque no todos los exportadores de EA generan XMI idéntico:
- Busca elementos por nombre local de tag (ignora el namespace exacto: uml:Class, Class, etc.)
- Acepta el tipo de un atributo/parámetro tanto como atributo `type="idref"` como hijo <type xmi:idref="..."/>
- Reconoce clases, interfaces, enums, atributos, operaciones, parámetros,
  generalización (herencia), realización de interfaz, asociaciones (con agregación/composición)
  y dependencias.
"""
from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET

XMI_ID_KEYS = (
    "{http://schema.omg.org/spec/XMI/2.1}id",
    "{http://schema.omg.org/spec/XMI/2.1}idref",
    "{http://www.omg.org/XMI}id",
    "{http://www.omg.org/XMI}idref",
    "xmi:id",
    "xmi:idref",
)

VISIBILITY_MAP = {
    "public": "public",
    "private": "private",
    "protected": "protected",
    "package": "package",
    "+": "public",
    "-": "private",
    "#": "protected",
    "~": "package",
}


def _local(tag: str) -> str:
    name = tag.split("}", 1)[-1] if "}" in tag else tag
    # XMI 1.x de EA usa a veces atributos literales xmi.id/xmi.idref.
    return name.rsplit(":", 1)[-1].rsplit(".", 1)[-1]


def _xmi_type(el) -> str:
    """Devuelve el nombre corto del xmi:type (p.ej. 'Class' para el valor 'uml:Class').
    El VALOR del atributo es texto literal (no se resuelve como namespace), así que
    solo hace falta quitarle el prefijo 'uml:' si lo tiene.
    """
    for key, value in el.attrib.items():
        if _local(key) == "type" and key != "type":
            return value.split(":", 1)[-1] if value else ""
    return ""


def _uml_type(el) -> str:
    return _xmi_type(el) or _local(el.tag)


def _definition_id(el):
    # Una referencia no debe sustituir al elemento que define ese identificador.
    return next((value for key, value in el.attrib.items() if _local(key) == "id"), None)


def _get_id(el):
    for key in XMI_ID_KEYS:
        if key in el.attrib:
            return el.attrib[key]
    for key, value in el.attrib.items():
        if _local(key) in ("id", "idref"):
            return value
    return None


def _get_idref(el):
    for key, value in el.attrib.items():
        if _local(key) == "idref":
            return value
    return None


def _element_key(el):
    return _get_id(el) or f"__synthetic_{id(el)}"


def _get_idref_from_child_or_attr(el, tag_name: str, attr_name: str = "type"):
    """Busca una referencia de tipo, sea como atributo directo o como <tag xmi:idref="..."/>."""
    if attr_name in el.attrib:
        return el.attrib[attr_name]
    for child in el:
        if _local(child.tag) == tag_name:
            ref = _get_id(child)
            if ref:
                return ref
    return None


def _iter_by_local_tag(root, tag_name: str):
    """Elementos cuyo NOMBRE DE TAG coincide (generalization, interfaceRealization, ownedAttribute...)."""
    for el in root.iter():
        if _local(el.tag) == tag_name:
            yield el


def _iter_by_xmi_type(root, type_name: str):
    """Elementos cuyo atributo xmi:type coincide (uml:Class, uml:Association, uml:Dependency...).
    Estos suelen venir como <packagedElement xmi:type="uml:...">.
    """
    for el in root.iter():
        if _xmi_type(el) == type_name:
            yield el


def _extract_xml_bytes(payload: bytes) -> bytes:
    """Acepta XML plano o un archivo ZIP legado que contenga XML/XMI."""
    max_xml_bytes = 16 * 1024 * 1024
    if len(payload) > max_xml_bytes:
        raise ET.ParseError("El archivo supera el límite de 16 MiB.")
    try:
        ET.fromstring(payload)
        return payload
    except ET.ParseError:
        pass

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            candidates = sorted(
                (info for info in archive.infolist() if info.filename.lower().endswith((".xml", ".xmi", ".txt", ".dat"))),
                key=lambda info: not info.filename.lower().endswith((".xml", ".xmi")),
            )
            total_bytes = 0
            for info in candidates:
                total_bytes += info.file_size
                if total_bytes > max_xml_bytes:
                    raise ET.ParseError("El XML descomprimido supera el límite de 16 MiB.")
                candidate = archive.read(info)
                try:
                    ET.fromstring(candidate)
                    return candidate
                except ET.ParseError:
                    continue
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
        pass

    raise ET.ParseError("No se encontró un XML/XMI válido dentro del archivo.")


def parse_xmi_to_spec(xml_bytes: bytes) -> dict:
    """Parsea XMI en dos pasadas y devuelve nombres, no referencias XML."""
    root = ET.fromstring(_extract_xml_bytes(xml_bytes))
    elements = {_definition_id(el): el for el in root.iter() if _definition_id(el)}
    class_elements = {
        _element_key(el): el
        for el in root.iter()
        if _uml_type(el) in {"Class", "Interface", "Enumeration"} and el.get("name")
    }
    class_names = {key: el.get("name") for key, el in class_elements.items()}
    type_names = {
        key: el.get("name")
        for key, el in elements.items()
        if _uml_type(el) in {"PrimitiveType", "DataType"} and el.get("name")
    }

    def resolve_reference(value: str | None, href: str | None = None) -> str:
        if value:
            value = value.split("#")[-1]
            return class_names.get(value) or type_names.get(value) or value
        if href:
            return href.rstrip("/").split("/")[-1].split("#")[-1] or "String"
        return "String"

    def reference(el, child_name: str = "type") -> str:
        direct = el.get(child_name)
        href = el.get("href") if child_name == "type" else None
        if direct or href:
            return resolve_reference(direct, href)
        for child in el.iter():
            if child is el:
                continue
            if _local(child.tag) in {child_name, "Classifier", "DataType", "PrimitiveType", "Class"}:
                ref = _get_idref(child)
                if ref or child.get("href"):
                    return resolve_reference(ref, child.get("href"))
        return "String"

    def visibility(value: str | None, default: str) -> str:
        return VISIBILITY_MAP.get((value or default).lower(), default)

    def kind(el) -> str:
        element_type = _uml_type(el)
        if element_type == "Interface":
            return "INTERFACE"
        if element_type == "Enumeration":
            return "ENUM"
        if el.get("isAbstract", "false").lower() == "true":
            return "ABSTRACT"
        return "CLASS"

    classes = []
    for class_id, class_el in class_elements.items():
        item = {"name": class_el.get("name"), "kind": kind(class_el), "attributes": [], "methods": []}
        for child in class_el.iter():
            if child is class_el:
                continue
            local = _local(child.tag)
            if local in {"ownedAttribute", "Attribute"}:
                item["attributes"].append({
                    "name": child.get("name", "atributo"),
                    "type": reference(child),
                    "visibility": visibility(child.get("visibility"), "private"),
                    "is_static": child.get("isStatic", "false").lower() == "true",
                })
            elif local in {"ownedOperation", "Operation"}:
                parameters = []
                return_type = "void"
                for parameter in child.iter():
                    if _local(parameter.tag) not in {"ownedParameter", "Parameter"}:
                        continue
                    parameter_type = reference(parameter)
                    if (parameter.get("direction") or parameter.get("kind") or "in").lower() == "return":
                        return_type = parameter_type
                    else:
                        parameters.append(f"{parameter.get('name', 'param')}: {parameter_type}")
                item["methods"].append({
                    "name": child.get("name", "metodo"),
                    "returnType": return_type,
                    "visibility": visibility(child.get("visibility"), "public"),
                    "parameters": parameters,
                    "is_static": child.get("isStatic", "false").lower() == "true",
                })
            elif local == "ownedLiteral":
                item["attributes"].append({"name": child.get("name", "valor"), "type": "String", "visibility": "public"})
        classes.append(item)

    def multiplicity(end) -> str:
        if end.get("multiplicity"):
            return end.get("multiplicity").replace("-1", "*")
        lower = upper = None
        for child in end.iter():
            local = _local(child.tag)
            if local == "lowerValue":
                lower = child.get("value")
            elif local == "upperValue":
                upper = child.get("value")
            elif local == "MultiplicityRange":
                lower = child.get("lower", lower)
                upper = child.get("upper", upper)
        lower = lower if lower is not None else "1"
        upper = upper if upper is not None else "1"
        if upper in {"*", "-1"}:
            return f"{lower}..*"
        if lower == upper:
            return upper
        return f"{lower}..{upper}"

    relations = []
    for owner_id, owner in class_elements.items():
        for child in owner:
            local = _local(child.tag)
            if local == "generalization" and child.get("general") in class_names:
                relations.append({"from": class_names[owner_id], "to": class_names[child.get("general")], "type": "inheritance", "sourceMultiplicity": "1", "targetMultiplicity": "1", "label": ""})
            elif local == "interfaceRealization":
                target_id = child.get("contract") or child.get("supplier")
                if target_id in class_names:
                    relations.append({"from": class_names[owner_id], "to": class_names[target_id], "type": "realization", "sourceMultiplicity": "1", "targetMultiplicity": "1", "label": ""})

    # XMI 1.x suele declarar generalizaciones como elementos independientes.
    for element in root.iter():
        if _uml_type(element) != "Generalization":
            continue
        source_id = element.get("specific") or element.get("child") or element.get("subtype")
        target_id = element.get("general") or element.get("parent") or element.get("supertype")
        if source_id in class_names and target_id in class_names:
            relation = {"from": class_names[source_id], "to": class_names[target_id], "type": "inheritance", "sourceMultiplicity": "1", "targetMultiplicity": "1", "label": element.get("name", "")}
            if relation not in relations:
                relations.append(relation)

    for element in root.iter():
        element_type = _uml_type(element)
        if element_type == "Dependency":
            source = class_names.get(element.get("client"))
            target = class_names.get(element.get("supplier"))
            if source and target:
                relations.append({"from": source, "to": target, "type": "dependency", "sourceMultiplicity": "1", "targetMultiplicity": "1", "label": element.get("name", "")})
        elif element_type == "Association":
            end_ids = element.get("memberEnd", "").split()
            end_ids.extend(_get_id(child) for child in element if _local(child.tag) == "memberEnd" and _get_id(child))
            ends = [elements[end_id] for end_id in end_ids if end_id in elements]
            ends.extend(child for child in element.iter() if _local(child.tag) in {"ownedEnd", "AssociationEnd"})
            ends = list(dict.fromkeys(end for end in ends if _get_idref_from_child_or_attr(end, "type") in class_names))
            if len(ends) < 2:
                continue
            first, second = ends[:2]
            relation_type = "COMPOSITION" if any(end.get("aggregation", "").lower() in {"composite", "2"} for end in ends) else "AGGREGATION" if any(end.get("aggregation", "").lower() in {"shared", "aggregate", "1"} for end in ends) else "ASSOCIATION"
            relations.append({
                "from": class_names[_get_idref_from_child_or_attr(first, "type")], "to": class_names[_get_idref_from_child_or_attr(second, "type")], "type": relation_type,
                "sourceMultiplicity": multiplicity(first), "targetMultiplicity": multiplicity(second), "label": element.get("name", ""),
            })

    return {"classes": classes, "relations": relations}
