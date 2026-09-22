from rest_framework import serializers


class GenerarBackendRequestSerializer(serializers.Serializer):
    diagrama_id = serializers.IntegerField(min_value=1)
    incluir_swagger = serializers.BooleanField(default=True)
    incluir_docker = serializers.BooleanField(default=True)
    completar_pk = serializers.BooleanField(default=False)
    autocorregir = serializers.BooleanField(default=False)

    alcance = serializers.ChoiceField(choices=["entidades", "completo"], default="completo")


class GenerarFlutterRequestSerializer(serializers.Serializer):
    diagrama_id = serializers.IntegerField(min_value=1)
    api_base_url = serializers.URLField(default="http://10.0.2.2:8080", max_length=300)
    incluir_ia_local = serializers.BooleanField(default=True)
