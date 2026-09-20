from generador.exceptions import TipoNoSoportadoError

TIPO_UML_A_JAVA = {}
for java, aliases in {
    "String": ["string", "texto", "text", "texto_largo", "varchar"],
    "Integer": ["integer", "int", "numero", "numero_entero"],
    "Long": ["long", "numero_largo"],
    "BigDecimal": ["bigdecimal", "decimal", "numero_decimal"],
    "Double": ["double"], "Float": ["float"],
    "LocalDate": ["localdate", "date", "fecha"],
    "LocalDateTime": ["localdatetime", "datetime", "fecha_hora"],
    "Boolean": ["boolean", "bool", "booleano"],
    "UUID": ["uuid"],
}.items():
    for alias in aliases:
        TIPO_UML_A_JAVA[alias] = java


def mapear_tipo(tipo_uml):
    try:
        return TIPO_UML_A_JAVA[tipo_uml.strip().lower()]
    except KeyError:
        raise TipoNoSoportadoError(f"El tipo '{tipo_uml}' no tiene un mapeo Java soportado.") from None
