"""Exporta un diagrama UML como XMI 2.1 compatible con Enterprise Architect."""
import uuid
from xml.dom import minidom
from xml.etree import ElementTree as ET

XMI_NS = "http://www.omg.org/spec/XMI/20131001"
UML_NS = "http://www.omg.org/spec/UML/20131001"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

ET.register_namespace("xmi", XMI_NS)
ET.register_namespace("uml", UML_NS)
ET.register_namespace("xsi", XSI_NS)

VISIBILITY_MAP = {
    "PUBLIC": "public",
    "PRIVATE": "private",
    "PROTECTED": "protected",
    "PACKAGE": "package",
}

# Tipos primitivos UML "estándar" que EA reconoce sin problema
PRIMITIVE_TYPES = {"String", "Integer", "Boolean", "Real", "Long", "Double", "Float", "Date", "void"}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _xmi_type(el, value):
    el.set(f"{{{XMI_NS}}}type", value)


def _xmi_id(el, value):
    el.set(f"{{{XMI_NS}}}id", value)


def diagram_to_xmi(diagram) -> bytes:
    """Recibe una instancia de Diagram (con .classes y .relations precargados) y devuelve bytes XML."""
    classes = list(diagram.classes.all().prefetch_related("attributes", "methods"))
    relations = list(diagram.relations.all())

    root = ET.Element(f"{{{XMI_NS}}}XMI")
    root.set(f"{{{XMI_NS}}}version", "2.1")

    documentation = ET.SubElement(root, f"{{{XMI_NS}}}Documentation")
    documentation.set("exporter", "Diagramador UML")
    documentation.set("exporterVersion", "1.0")

    model = ET.SubElement(root, f"{{{UML_NS}}}Model")
    _xmi_type(model, "uml:Model")
    _xmi_id(model, _new_id("model"))
    model.set("name", diagram.name)
    model.set(f"{{{XSI_NS}}}schemaLocation", f"{XMI_NS} http://www.omg.org/spec/XMI/20131001 {UML_NS} http://www.omg.org/spec/UML/20131001")

    # EA importa de forma más consistente cuando el modelo está dentro de un paquete.
    package = ET.SubElement(model, "packagedElement")
    _xmi_type(package, "uml:Package")
    _xmi_id(package, _new_id("package"))
    package.set("name", diagram.name or "UML Model")

    class_id_map = {uml_class.id: _new_id("class") for uml_class in classes}
    class_type_ids = {uml_class.name: class_id_map[uml_class.id] for uml_class in classes}
    type_id_map = {}  # nombre de tipo primitivo -> xmi id generado

    def get_type_id(type_name: str) -> str:
        type_name = (type_name or "String").strip()
        if type_name in class_type_ids:
            return class_type_ids[type_name]
        if type_name not in type_id_map:
            type_el = ET.SubElement(package, "packagedElement")
            _xmi_type(type_el, "uml:PrimitiveType")
            new_id = _new_id("type")
            _xmi_id(type_el, new_id)
            type_el.set("name", type_name)
            type_id_map[type_name] = new_id
        return type_id_map[type_name]

    # ---- Primera pasada: crear el elemento de cada clase (para poder referenciarlas en relaciones) ----
    for uml_class in classes:
        xmi_id = class_id_map[uml_class.id]

        el = ET.SubElement(package, "packagedElement")
        if uml_class.kind == "INTERFACE":
            _xmi_type(el, "uml:Interface")
        elif uml_class.kind == "ENUM":
            _xmi_type(el, "uml:Enumeration")
        else:
            _xmi_type(el, "uml:Class")
            if uml_class.kind == "ABSTRACT":
                el.set("isAbstract", "true")
        _xmi_id(el, xmi_id)
        el.set("name", uml_class.name)

        if uml_class.kind == "ENUM":
            # En un enum, los "atributos" se modelan como literales del enum
            for attr in uml_class.attributes.all():
                lit = ET.SubElement(el, "ownedLiteral")
                _xmi_type(lit, "uml:EnumerationLiteral")
                _xmi_id(lit, _new_id("lit"))
                lit.set("name", attr.name)
        else:
            for attr in uml_class.attributes.all():
                attr_el = ET.SubElement(el, "ownedAttribute")
                _xmi_type(attr_el, "uml:Property")
                _xmi_id(attr_el, _new_id("attr"))
                attr_el.set("name", attr.name)
                attr_el.set("visibility", VISIBILITY_MAP.get(attr.visibility, "private"))
                if attr.is_static:
                    attr_el.set("isStatic", "true")
                type_ref = ET.SubElement(attr_el, "type")
                type_ref.set(f"{{{XMI_NS}}}idref", get_type_id(attr.data_type))

            for method in uml_class.methods.all():
                op_el = ET.SubElement(el, "ownedOperation")
                _xmi_type(op_el, "uml:Operation")
                _xmi_id(op_el, _new_id("op"))
                op_el.set("name", method.name)
                op_el.set("visibility", VISIBILITY_MAP.get(method.visibility, "public"))
                if method.is_static:
                    op_el.set("isStatic", "true")

                for param in method.parameters or []:
                    param_el = ET.SubElement(op_el, "ownedParameter")
                    _xmi_type(param_el, "uml:Parameter")
                    _xmi_id(param_el, _new_id("param"))
                    param_el.set("name", param.get("name", "param"))
                    param_el.set("direction", "in")
                    ptype_ref = ET.SubElement(param_el, "type")
                    ptype_ref.set(f"{{{XMI_NS}}}idref", get_type_id(param.get("type", "String")))

                if method.return_type and method.return_type.lower() != "void":
                    ret_el = ET.SubElement(op_el, "ownedParameter")
                    _xmi_type(ret_el, "uml:Parameter")
                    _xmi_id(ret_el, _new_id("param"))
                    ret_el.set("direction", "return")
                    rtype_ref = ET.SubElement(ret_el, "type")
                    rtype_ref.set(f"{{{XMI_NS}}}idref", get_type_id(method.return_type))

    # ---- Segunda pasada: relaciones ----
    for rel in relations:
        src_id = class_id_map.get(rel.source_id)
        tgt_id = class_id_map.get(rel.target_id)
        if not src_id or not tgt_id:
            continue

        if rel.relation_type == "INHERITANCE":
            # La herencia se representa DENTRO del elemento de la subclase (source hereda de target)
            source_el = root.find(f".//*[@{{{XMI_NS}}}id='{src_id}']")
            if source_el is not None:
                gen_el = ET.SubElement(source_el, "generalization")
                _xmi_type(gen_el, "uml:Generalization")
                _xmi_id(gen_el, _new_id("gen"))
                gen_el.set("general", tgt_id)

        elif rel.relation_type == "REALIZATION":
            source_el = root.find(f".//*[@{{{XMI_NS}}}id='{src_id}']")
            if source_el is not None:
                real_el = ET.SubElement(source_el, "interfaceRealization")
                _xmi_type(real_el, "uml:InterfaceRealization")
                _xmi_id(real_el, _new_id("real"))
                real_el.set("contract", tgt_id)
                real_el.set("client", src_id)
                real_el.set("supplier", tgt_id)

        elif rel.relation_type == "DEPENDENCY":
            dep_el = ET.SubElement(package, "packagedElement")
            _xmi_type(dep_el, "uml:Dependency")
            _xmi_id(dep_el, _new_id("dep"))
            dep_el.set("client", src_id)
            dep_el.set("supplier", tgt_id)
            if rel.label:
                dep_el.set("name", rel.label)

        else:
            # ASSOCIATION, AGGREGATION, COMPOSITION -> uml:Association con dos ownedEnd
            assoc_el = ET.SubElement(package, "packagedElement")
            _xmi_type(assoc_el, "uml:Association")
            assoc_id = _new_id("assoc")
            _xmi_id(assoc_el, assoc_id)
            if rel.label:
                assoc_el.set("name", rel.label)

            end1_id = _new_id("end")
            end2_id = _new_id("end")

            member1 = ET.SubElement(assoc_el, "memberEnd")
            member1.set(f"{{{XMI_NS}}}idref", end1_id)
            member2 = ET.SubElement(assoc_el, "memberEnd")
            member2.set(f"{{{XMI_NS}}}idref", end2_id)

            end1 = ET.SubElement(assoc_el, "ownedEnd")
            _xmi_type(end1, "uml:Property")
            _xmi_id(end1, end1_id)
            end1.set("type", src_id)
            end1.set("association", assoc_id)
            _add_multiplicity(end1, rel.multiplicity_source)

            end2 = ET.SubElement(assoc_el, "ownedEnd")
            _xmi_type(end2, "uml:Property")
            _xmi_id(end2, end2_id)
            end2.set("type", tgt_id)
            end2.set("association", assoc_id)
            if rel.relation_type == "AGGREGATION":
                end2.set("aggregation", "shared")
            elif rel.relation_type == "COMPOSITION":
                end2.set("aggregation", "composite")
            _add_multiplicity(end2, rel.multiplicity_target)

    xml_bytes = ET.tostring(root, encoding="utf-8")
    pretty = minidom.parseString(xml_bytes).toprettyxml(indent="  ", encoding="utf-8")
    return pretty


def _add_multiplicity(end_el, mult: str):
    mult = (mult or "1").strip()
    lower, upper = "1", "1"
    if mult == "*":
        lower, upper = "0", "*"
    elif "..." in mult or ".." in mult:
        parts = mult.replace("...", "..").split("..")
        lower, upper = parts[0] or "0", parts[1] or "*"
    else:
        lower = upper = mult

    lower_el = ET.SubElement(end_el, "lowerValue")
    _xmi_type(lower_el, "uml:LiteralInteger")
    _xmi_id(lower_el, _new_id("lo"))
    lower_el.set("value", "0" if lower == "*" else lower)

    upper_el = ET.SubElement(end_el, "upperValue")
    _xmi_type(upper_el, "uml:LiteralUnlimitedNatural")
    _xmi_id(upper_el, _new_id("up"))
    upper_el.set("value", upper)
