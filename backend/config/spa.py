"""Sirve el build de React (index.html) para cualquier ruta del frontend.

El archivo se lee del disco y se devuelve tal cual (no es una plantilla de Django);
los assets los sirve WhiteNoise bajo /static/.
"""
from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound
from django.views.decorators.http import require_GET


@require_GET
def spa(request, ruta=""):
    indice = settings.FRONTEND_DIST / "index.html"
    try:
        contenido = indice.read_text(encoding="utf-8")
    except FileNotFoundError:
        return HttpResponseNotFound(
            "No se encontró el build del frontend (index.html). Ejecute `npm run build` en frontend/ "
            "o defina FRONTEND_DIST.",
            content_type="text/plain; charset=utf-8",
        )
    return HttpResponse(contenido, content_type="text/html; charset=utf-8")
