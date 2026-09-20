from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    ProjectViewSet, DiagramViewSet, UMLClassViewSet,
    AttributeViewSet, MethodViewSet, RelationViewSet, import_xmi,
    register, login, logout, current_user, interpret_uml, accept_share,
)

router = DefaultRouter()
router.register(r"projects", ProjectViewSet)
router.register(r"diagrams", DiagramViewSet)
router.register(r"classes", UMLClassViewSet)
router.register(r"attributes", AttributeViewSet)
router.register(r"methods", MethodViewSet)
router.register(r"relations", RelationViewSet)

urlpatterns = [
    path("auth/register/", register, name="register"),
    path("auth/login/", login, name="login"),
    path("auth/logout/", logout, name="logout"),
    path("auth/me/", current_user, name="current-user"),
    path("ai/interpret-uml/", interpret_uml, name="interpret-uml"),
    path("ai/import-xmi/", import_xmi, name="import-xmi"),
    path("shares/<uuid:token>/accept/", accept_share, name="accept-share"),
    *router.urls,
]
