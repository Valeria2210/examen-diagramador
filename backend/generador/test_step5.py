import copy
import tempfile
from pathlib import Path
from zipfile import ZipFile
from django.test import SimpleTestCase, override_settings
from .demo_step3 import demo_ir
from .exceptions import ValidacionIRError
from .services.code_generator import CodeGenerator
from .services.validator import ValidadorIR
from .services.relation_helpers import nombre_tabla_intermedia


class RelationsTests(SimpleTestCase):
    def test_relationship_validation_and_distinct_associations(self):
        ir = demo_ir()
        for value, message in (("", "ambos lados"), ("supervisor", "Autorrelación")):
            invalid = copy.deepcopy(ir)
            invalid["relaciones"][-1]["nombre_campo_destino"] = value
            with self.assertRaisesMessage(ValidacionIRError, message):
                ValidadorIR(invalid).validar()
        duplicate = copy.deepcopy(ir)
        duplicate["relaciones"].append(copy.deepcopy(ir["relaciones"][0]))
        with self.assertRaisesMessage(ValidacionIRError, "duplicada"):
            ValidadorIR(duplicate).validar()
        reversed_rel = {"origen": "Pedido", "destino": "Cliente", "tipo": "ManyToOne",
            "nombre_campo_origen": "cliente", "nombre_campo_destino": "pedidos"}
        duplicate["relaciones"][-1] = reversed_rel
        with self.assertRaisesMessage(ValidacionIRError, "duplicada"):
            ValidadorIR(duplicate).validar()
        extra = copy.deepcopy(ir["relaciones"][0])
        extra.update(nombre_campo_origen="pedidosFacturados", nombre_campo_destino="clienteFacturacion")
        ir["relaciones"].append(extra)
        ValidadorIR(ir).validar()

    def test_join_table_is_short_stable_and_distinguishes_fields(self):
        rel = demo_ir()["relaciones"][2]
        name = nombre_tabla_intermedia(rel)
        self.assertEqual(name, nombre_tabla_intermedia(copy.deepcopy(rel)))
        self.assertLessEqual(len(name), 63)
        self.assertNotEqual(name, nombre_tabla_intermedia({**rel, "nombre_campo_origen": "otrasEtiquetas"}))
        self.assertLessEqual(len(nombre_tabla_intermedia({k: "A" * 50 for k in rel})), 63)

    def test_generation_covers_both_directions_and_lazy_loading(self):
        for reverse in (False, True):
            ir = demo_ir()
            if reverse:
                rel = ir["relaciones"][0]
                ir["relaciones"][0] = {"origen": rel["destino"], "destino": rel["origen"], "tipo": "ManyToOne",
                    "nombre_campo_origen": rel["nombre_campo_destino"], "nombre_campo_destino": rel["nombre_campo_origen"]}
            with tempfile.TemporaryDirectory() as temp, override_settings(GENERADOR_TMP_DIR=Path(temp)):
                name = CodeGenerator(ir).generar()
                with ZipFile(Path(temp) / name) as archive:
                    base = "src/main/java/com/generado/ventasdemo/"
                    cliente = archive.read(base + "entidades/Cliente.java").decode()
                    pedido = archive.read(base + "entidades/Pedido.java").decode()
                    perfil = archive.read(base + "entidades/Perfil.java").decode()
                    self.assertIn('@OneToMany(mappedBy = "cliente", fetch = FetchType.LAZY)', cliente)
                    self.assertIn('@ManyToOne(fetch = FetchType.LAZY)', pedido)
                    self.assertIn('@OneToOne(mappedBy = "perfil", fetch = FetchType.LAZY)', perfil)
                    for entity in ("Cliente", "Pedido", "Perfil", "Etiqueta"):
                        source = archive.read(base + "entidades/" + entity + ".java").decode()
                        for line in source.splitlines():
                            if any("@" + kind + "(" in line for kind in ("ManyToOne", "OneToMany", "OneToOne", "ManyToMany")):
                                self.assertIn("FetchType.LAZY", line)
                    mapper = archive.read(base + "mappers/PedidoMapper.java").decode()
                    self.assertIn('@Mapping(target = "cliente", ignore = true)', mapper)
                    dto = archive.read(base + "dto/ClienteDTO.java").decode()
                    self.assertIn("private UUID perfilId;", dto)
                    service = archive.read(base + "servicios/PedidoService.java").decode()
                    self.assertIn("findAllById(ids)", service)
                    self.assertIn("!byId.containsKey(id)", service)
                    self.assertIn("@Transactional", service)
                    self.assertIn("entidad.getEtiquetas().clear()", service)
                    self.assertIn("repository.eliminarPorId(id)", service)
                    repository = archive.read(base + "repositorios/ClienteRepository.java").decode()
                    self.assertIn("@EntityGraph", repository)
                    self.assertNotIn('"pedidos"', repository)
