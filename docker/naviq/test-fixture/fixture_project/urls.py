from django.http import HttpResponse
from django.urls import path


def root(request):
    return HttpResponse("ok")


urlpatterns = [path("", root)]
