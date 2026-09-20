from django.contrib import admin
from .models import Project, Diagram, UMLClass, Attribute, Method, Relation

admin.site.register(Project)
admin.site.register(Diagram)
admin.site.register(UMLClass)
admin.site.register(Attribute)
admin.site.register(Method)
admin.site.register(Relation)
