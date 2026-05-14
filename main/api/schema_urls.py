from django.urls import include, path

urlpatterns = [
    path("api/plugins/config-weaver/", include("main.api.urls")),
]
