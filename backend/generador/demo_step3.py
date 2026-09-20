"""Generate reproducible examples without modifying the diagram database.

Run through manage.py shell, with DEBUG=True and DB_ENGINE=postgres.
"""
import copy
from pathlib import Path
from zipfile import ZipFile
from django.conf import settings
from generador.services.code_generator import CodeGenerator


def attr(nombre, tipo, pk=False, nullable=True, unico=False, longitud=None):
    return {"nombre": nombre, "tipo": tipo, "pk": pk, "autogenerado": pk and tipo in ("Long", "Integer", "UUID"),
        "nullable": nullable and not pk, "unico": unico, "longitud": longitud, "texto_largo": False}


def demo_ir():
    return {"proyecto": {"nombre": "ventasdemo", "paquete_base": "com.generado.ventasdemo"},
        "entidades": [
            {"nombre": "Cliente", "atributos": [attr("codigoCliente", "Long", True), attr("nombre", "String", nullable=False, longitud=80), attr("email", "String", unico=True, longitud=100)]},
            {"nombre": "Pedido", "atributos": [attr("codigoPedido", "Integer", True), attr("total", "BigDecimal", nullable=False), attr("fecha", "LocalDate"), attr("creado", "LocalDateTime"), attr("pagado", "Boolean")]},
            {"nombre": "Perfil", "atributos": [attr("clavePerfil", "UUID", True), attr("descripcion", "String")]},
            {"nombre": "Etiqueta", "atributos": [attr("codigo", "String", True), attr("nombre", "String", nullable=False)]}],
        "relaciones": [
            {"origen": "Cliente", "destino": "Pedido", "tipo": "OneToMany", "nombre_campo_origen": "pedidos", "nombre_campo_destino": "cliente"},
            {"origen": "Cliente", "destino": "Perfil", "tipo": "OneToOne", "nombre_campo_origen": "perfil", "nombre_campo_destino": "cliente"},
            {"origen": "Pedido", "destino": "Etiqueta", "tipo": "ManyToMany", "nombre_campo_origen": "etiquetas", "nombre_campo_destino": "pedidos"},
            {"origen": "Cliente", "destino": "Cliente", "tipo": "ManyToOne", "nombre_campo_origen": "supervisor", "nombre_campo_destino": "subordinados"}]}


if __name__ == "__main__":
    root = settings.BASE_DIR / "artifacts" / "step3-demo"
    if root.exists():
        raise RuntimeError("El ejemplo ya existe; usa otra carpeta para conservar el anterior.")
    name = CodeGenerator(copy.deepcopy(demo_ir())).generar()
    with ZipFile(Path(settings.GENERADOR_TMP_DIR) / name) as archive:
        archive.extractall(root)
    print("Example project:", root)
    print("ZIP:", name)
