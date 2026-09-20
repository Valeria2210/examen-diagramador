from rest_framework import serializers


class GenerarBackendRequestSerializer(serializers.Serializer):
    diagrama_id = serializers.IntegerField(min_value=1)
    incluir_swagger = serializers.BooleanField(default=True)
    incluir_docker = serializers.BooleanField(default=True)
    completar_pk = serializers.BooleanField(default=False)
    autocorregir = serializers.BooleanField(default=False)

    alcance = serializers.ChoiceField(choices=["entidades", "completo"], default="completo")
