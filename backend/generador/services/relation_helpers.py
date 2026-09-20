import hashlib


def nombre_tabla_intermedia(rel):
    """Stable PostgreSQL identifier, also for multiple associations/self-relations."""
    parts = [rel[k] for k in ("origen", "nombre_campo_origen", "destino", "nombre_campo_destino")]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return "uml_rel_" + digest
