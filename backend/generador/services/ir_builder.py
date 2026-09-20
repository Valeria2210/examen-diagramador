import re
import unicodedata
from generador.exceptions import DiagramaVacioError, ValidacionIRError
from .type_mapping import mapear_tipo

JAVA_RESERVED = set("abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for goto if implements import instanceof int interface long native new package private protected public return short static strictfp super switch synchronized this throw throws transient try void volatile while true false null record sealed permits var yield".split())
ENTITY_RESERVED = set("String Integer Long UUID List ArrayList BigDecimal Boolean Double Float LocalDate LocalDateTime Application Entity Table Column Id GeneratedValue Service Mapper Mapping MappingTarget ResponseEntity ResourceNotFoundException GlobalExceptionHandler RequestMapping RestController".split())
ENTITY_RESERVED.update("Objects LinkedHashSet Collectors Optional BatchSize JsonIgnore JsonProperty NotNull Size JpaRepository Modifying Query Param EntityGraph Transactional ResponseStatusException HttpStatus Valid GetMapping PostMapping PutMapping DeleteMapping PathVariable RequestBody ReportingPolicy GenerationType FetchType JoinColumn JoinTable ManyToOne OneToMany OneToOne ManyToMany".split())


def normalizar(texto, clase=False):
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", texto)
    texto = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", texto)
    palabras = re.findall(r"[A-Za-z0-9]+", texto)
    nombre = "".join(p.lower().capitalize() for p in palabras)
    if not clase:
        nombre = nombre[:1].lower() + nombre[1:]
    if not nombre or nombre[0].isdigit() or nombre in JAVA_RESERVED:
        raise ValidacionIRError(f"Nombre Java inválido: '{texto}'.")
    return nombre


def cardinalidad(valor):
    if valor in ("1", "0..1"):
        return False
    if valor in ("*", "0..*", "1..*"):
        return True
    raise ValidacionIRError(f"Multiplicidad no soportada: '{valor}'. Usa 1, 0..1, *, 0..* o 1..*.")


class IRBuilder:
    def __init__(self, diagrama, completar_pk=False, autocorregir=False):
        self.diagrama = diagrama
        self.autocorregir = autocorregir
        self.completar_pk = completar_pk or autocorregir
        self.avisos = []

    def _nombre(self, texto, usados, contexto, clase=False, limite=50):
        if not self.autocorregir:
            return normalizar(texto, clase)
        try:
            nombre = normalizar(texto, clase)
        except ValidacionIRError:
            nombre = normalizar(("Clase " if clase else "campo ") + texto, clase)
        if clase and nombre in ENTITY_RESERVED:
            nombre += "Modelo"
        nombre = nombre[:limite]
        if nombre in JAVA_RESERVED:
            nombre = (nombre + "Campo")[:limite]
        base, numero = nombre, 2
        while nombre.lower() in usados:
            sufijo = str(numero); numero += 1
            nombre = base[:limite - len(sufijo)] + sufijo
        usados.add(nombre.lower())
        if nombre != texto:
            self.avisos.append(f"{contexto}: nombre '{texto}' convertido a '{nombre}'.")
        return nombre

    def _multiplicidad(self, valor):
        if self.autocorregir:
            limpio = re.sub(r"\s+", "", valor).lower()
            corregido = {"n": "*", "m": "*", "0..n": "0..*", "1..n": "1..*", "0..m": "0..*", "1..m": "1..*"}.get(limpio, limpio)
            if corregido != valor:
                self.avisos.append(f"Multiplicidad '{valor}' convertida a '{corregido}'.")
            valor = corregido
        return cardinalidad(valor), valor in ("1", "1..*")

    def construir(self):
        clases = sorted(self.diagrama.classes.all(), key=lambda c: c.pk)
        if not clases:
            raise DiagramaVacioError("El diagrama está vacío. Agrega al menos una clase.")
        usados = set()
        nombres = {c.pk: self._nombre(c.name, usados, f"Clase #{c.pk}", True) for c in clases}
        proyecto = self._nombre(self.diagrama.name, set(), "Proyecto")
        entidades = []
        for clase in clases:
            if clase.kind != "CLASS":
                raise ValidacionIRError(f"'{clase.name}': por ahora solo se generan entidades CLASS; {clase.kind} requiere otra estrategia.")
            atributos = []
            campos_usados = set()
            for attr in sorted(clase.attributes.all(), key=lambda a: (a.order, a.pk)):
                if attr.is_static:
                    raise ValidacionIRError(f"'{clase.name}.{attr.name}': un atributo static no es un campo persistente soportado.")
                tipo_uml, longitud = attr.data_type, attr.longitud
                if self.autocorregir:
                    limpio = tipo_uml.strip().lower()
                    match = re.fullmatch(r"(?:varchar|char|nvarchar)\s*\((\d+)\)", limpio)
                    if match:
                        tipo_uml = "String"
                        if longitud is None: longitud = int(match[1])
                    else:
                        aliases = {"bigint": "Long", "smallint": "Integer", "timestamp": "LocalDateTime",
                            "java.util.uuid": "UUID", "java.time.localdate": "LocalDate", "java.time.localdatetime": "LocalDateTime",
                            "java.math.bigdecimal": "BigDecimal"}
                        aliases.update({f"java.lang.{t.lower()}": t for t in ("String", "Integer", "Long", "Boolean", "Double", "Float")})
                        tipo_uml = aliases.get(limpio, tipo_uml)
                tipo = mapear_tipo(tipo_uml)
                if self.autocorregir and tipo != attr.data_type:
                    self.avisos.append(f"{clase.name}.{attr.name}: tipo '{attr.data_type}' convertido a '{tipo}'.")
                if self.autocorregir and longitud is not None and (tipo != "String" or longitud < 1):
                    self.avisos.append(f"{clase.name}.{attr.name}: longitud incompatible retirada.")
                    longitud = None
                atributos.append({"nombre": self._nombre(attr.name, campos_usados, f"{clase.name}.{attr.name}"), "tipo": tipo,
                    "pk": attr.es_pk, "autogenerado": attr.es_pk and tipo in ("Long", "Integer", "UUID"),
                    "nullable": False if attr.es_pk else attr.nullable, "unico": attr.es_unico,
                    "longitud": longitud, "texto_largo": attr.data_type.strip().lower() in ("texto_largo", "text")})
            if self.completar_pk and not any(a["pk"] for a in atributos):
                # Reuse only an unambiguous conventional identifier; never guess
                # from foreign keys such as idProfesor on Curso.
                candidatos = [a for a in atributos if a["nombre"].lower() in
                    {"id", ("id" + nombres[clase.pk]).lower(), (nombres[clase.pk] + "id").lower()}
                    and a["tipo"] in ("Long", "Integer", "UUID", "String")]
                if len(candidatos) == 1:
                    pk = candidatos[0]
                    pk.update(pk=True, nullable=False, autogenerado=pk["tipo"] != "String")
                else:
                    existentes = {a["nombre"].lower() for a in atributos}
                    nombre_pk = "id"
                    while nombre_pk.lower() in existentes:
                        nombre_pk += "Generado"
                    pk = {"nombre": nombre_pk, "tipo": "Long", "pk": True, "autogenerado": True,
                        "nullable": False, "unico": False, "longitud": None, "texto_largo": False}
                    atributos.insert(0, pk)
                self.avisos.append(f"{nombres[clase.pk]}: se usa {pk['nombre']} ({pk['tipo']}) como PK en el backend generado.")
            entidades.append({"nombre": nombres[clase.pk], "atributos": atributos})
        relaciones = []
        campos = {e["nombre"]: {a["nombre"].lower() for a in e["atributos"]} for e in entidades}
        dto_campos = {nombre: set(valores) for nombre, valores in campos.items()}
        for rel in sorted(self.diagrama.relations.all(), key=lambda r: r.pk):
            if rel.source_id not in nombres or rel.target_id not in nombres:
                raise ValidacionIRError("Una relación contiene clases de otro diagrama.")
            if rel.relation_type not in ("ASSOCIATION", "AGGREGATION", "COMPOSITION"):
                raise ValidacionIRError(f"Relación {rel.relation_type} no soportada para persistencia en este paso.")
            muchos_origen, obligatorio_origen = self._multiplicidad(rel.multiplicity_source)
            muchos_destino, obligatorio_destino = self._multiplicidad(rel.multiplicity_target)
            origen, destino = nombres[rel.source_id], nombres[rel.target_id]
            extremos = {}
            for rol, entidad, otro, muchos in (("origen", origen, destino, muchos_destino), ("destino", destino, origen, muchos_origen)):
                texto = getattr(rel, f"nombre_campo_{rol}") or (otro + ("s" if muchos else ""))
                if self.autocorregir:
                    sufijo = "Ids" if muchos else "Id"
                    # Entity and DTO names must both remain unique.
                    reservados = campos[entidad] | {n[:-len(sufijo)] for n in dto_campos[entidad] if n.endswith(sufijo.lower())}
                    campo = self._nombre(texto, reservados, f"Relación #{rel.pk}, {rol}", limite=45)
                    campos[entidad].add(campo.lower()); dto_campos[entidad].add((campo + sufijo).lower())
                else:
                    campo = normalizar(texto)
                extremos[f"nombre_campo_{rol}"] = campo
            relaciones.append({"origen": origen, "destino": destino,
                "tipo": {(False, False): "OneToOne", (False, True): "OneToMany", (True, False): "ManyToOne", (True, True): "ManyToMany"}[(muchos_origen, muchos_destino)],
                "semantica": rel.relation_type,
                "requerida_origen": obligatorio_destino,
                "requerida_destino": obligatorio_origen,
                **extremos})
        return {"proyecto": {"nombre": proyecto.lower(), "paquete_base": f"com.generado.{proyecto.lower()}"},
                "entidades": entidades, "relaciones": relaciones}
