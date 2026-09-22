from django.http import HttpResponse
from django.urls import path


def health(request):
    """The healthcheck in docker/naviq/Dockerfile expects a 200 at GET /."""
    return HttpResponse("naviq-stub OK")


urlpatterns = [
    path("", health),
]
