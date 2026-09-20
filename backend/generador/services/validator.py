import re
from django.conf import settings
from generador.exceptions import ValidacionIRError
from .ir_builder import normalizar, ENTITY_RESERVED


class ValidadorIR:
    def __init__(self, ir):
        self.ir = ir

    def validar(self):
        proyecto = self.ir["proyecto"]
        if not re.fullmatch(r"[a-z][a-z0-9]{0,49}", proyecto["nombre"]) or not re.fullmatch(r"[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)+", proyecto["paquete_base"]):
            raise ValidacionIRError("Nombre de proyecto o paquete Java inválido; usa hasta 50 caracteres normalizados para el proyecto.")
        entidades = self.ir["entidades"]
        if len(self.ir["relaciones"]) > settings.GENERADOR_MAX_RELACIONES:
            raise ValidacionIRError(f"Máximo {settings.GENERADOR_MAX_RELACIONES} relaciones por generación.")
        if not entidades or len(entidades) > settings.GENERADOR_MAX_ENTIDADES:
            raise ValidacionIRError(f"El diagrama debe contener entre 1 y {settings.GENERADOR_MAX_ENTIDADES} entidades.")
        nombres = [e["nombre"] for e in entidades]
        if len(set(n.lower() for n in nombres)) != len(nombres):
            raise ValidacionIRError("Hay nombres de clase duplicados después de normalizar.")
        campos = {}
        for e in entidades:
            normalizar(e["nombre"], True)
            if e["nombre"] in ENTITY_RESERVED or len(e["nombre"]) > 50 or not re.fullmatch(r"[A-Z][A-Za-z0-9]*", e["nombre"]):
                raise ValidacionIRError(f"Nombre de entidad reservado o demasiado largo: {e['nombre']}.")
            attrs = e["atributos"]
            if len(attrs) > settings.GENERADOR_MAX_ATRIBUTOS:
                raise ValidacionIRError(f"Máximo {settings.GENERADOR_MAX_ATRIBUTOS} atributos por entidad.")
            pks = [a for a in attrs if a["pk"]]
            if len(pks) != 1:
                raise ValidacionIRError(f"'{e['nombre']}' debe tener exactamente un atributo marcado como PK.")
            if pks[0]["tipo"] not in ("Long", "Integer", "UUID", "String"):
                raise ValidacionIRError(f"PK de '{e['nombre']}': usa Long, Integer, UUID o String.")
            fields = [a["nombre"] for a in attrs]
            if len(fields) != len(set(f.lower() for f in fields)):
                raise ValidacionIRError(f"Campos duplicados en '{e['nombre']}'.")
            for attr in attrs:
                normalizar(attr["nombre"])
                if not re.fullmatch(r"[a-z][A-Za-z0-9]{0,49}", attr["nombre"]) or attr["tipo"] not in {"String", "Integer", "Long", "BigDecimal", "Double", "Float", "Boolean", "UUID", "LocalDate", "LocalDateTime"}:
                    raise ValidacionIRError("Nombre de atributo inválido, demasiado largo o tipo Java no soportado.")
                if attr["longitud"] is not None and (attr["tipo"] != "String" or attr["longitud"] < 1):
                    raise ValidacionIRError("La longitud debe ser positiva y solo aplica a String.")
            campos[e["nombre"]] = set(fields)
        relaciones_vistas = set()
        for rel in self.ir["relaciones"]:
            if rel["origen"] not in campos or rel["destino"] not in campos:
                raise ValidacionIRError("Relación huérfana.")
            if rel["tipo"] not in ("OneToOne", "OneToMany", "ManyToOne", "ManyToMany"):
                raise ValidacionIRError("Tipo de relación no soportado.")
            if rel.get("semantica", "ASSOCIATION") not in ("ASSOCIATION", "AGGREGATION", "COMPOSITION"):
                raise ValidacionIRError("Semántica de relación no soportada.")
            if rel.get("semantica") == "COMPOSITION" and rel["tipo"] == "ManyToMany":
                raise ValidacionIRError("Una composición ManyToMany es ambigua; modela una entidad intermedia.")
            if not rel.get("nombre_campo_origen") or not rel.get("nombre_campo_destino"):
                raise ValidacionIRError("Define nombres de campo en ambos lados de la relación.")
            if rel["origen"] == rel["destino"] and rel["nombre_campo_origen"].lower() == rel["nombre_campo_destino"].lower():
                raise ValidacionIRError(f"Autorrelación en '{rel['origen']}': usa campos distintos, por ejemplo jefe y subordinados.")
            many_origen = rel["tipo"] in ("OneToMany", "ManyToMany")
            many_destino = rel["tipo"] in ("ManyToOne", "ManyToMany")
            key = tuple(sorted(((rel["origen"], rel["nombre_campo_origen"], many_origen),
                (rel["destino"], rel["nombre_campo_destino"], many_destino))))
            if key in relaciones_vistas:
                raise ValidacionIRError(f"Relación duplicada entre '{rel['origen']}' y '{rel['destino']}'.")
            relaciones_vistas.add(key)
            for entidad, campo in ((rel["origen"], rel["nombre_campo_origen"]), (rel["destino"], rel["nombre_campo_destino"])):
                normalizar(campo)
                if not re.fullmatch(r"[a-z][A-Za-z0-9]{0,44}", campo):
                    raise ValidacionIRError("Nombre de campo de relación inválido o demasiado largo (máximo 45 caracteres).")
                if campo in campos[entidad]:
                    raise ValidacionIRError(f"El campo de relación '{entidad}.{campo}' colisiona con otro campo.")
                campos[entidad].add(campo)
        dto_campos = {e["nombre"]: {a["nombre"] for a in e["atributos"]} for e in entidades}
        for rel in self.ir["relaciones"]:
            for rol, many in (("origen", rel["tipo"] in ("OneToMany", "ManyToMany")), ("destino", rel["tipo"] in ("ManyToOne", "ManyToMany"))):
                campo = rel[f"nombre_campo_{rol}"] + ("Ids" if many else "Id")
                if campo in dto_campos[rel[rol]]:
                    raise ValidacionIRError(f"El campo DTO '{rel[rol]}.{campo}' colisiona con otro campo.")
                dto_campos[rel[rol]].add(campo)
