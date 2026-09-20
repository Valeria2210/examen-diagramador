class GeneradorBaseError(Exception):
    codigo_http = 500


class TipoNoSoportadoError(GeneradorBaseError):
    codigo_http = 400


class ValidacionIRError(GeneradorBaseError):
    codigo_http = 400


class DiagramaVacioError(GeneradorBaseError):
    codigo_http = 400


class ErrorGeneracionCodigoError(GeneradorBaseError):
    codigo_http = 500
