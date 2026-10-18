# -*- coding: utf-8 -*-
"""Panel de administracion: permite revisar los datos recibidos."""
from django.contrib import admin

from .models import ConsolaAmbient, Estacion, Lectura


@admin.register(Estacion)
class EstacionAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "campus", "latitud", "longitud", "activa")
    list_filter = ("activa",)
    search_fields = ("nombre", "campus")


@admin.register(Lectura)
class LecturaAdmin(admin.ModelAdmin):
    list_display = ("estacion", "timestamp", "temperatura", "humedad_relativa",
                    "precipitacion", "presion_barometrica", "velocidad_viento",
                    "direccion_viento", "radiacion_solar")
    list_filter = ("estacion",)
    date_hierarchy = "timestamp"
    # Solo lectura: los datos llegan por el endpoint, no se editan a mano.
    readonly_fields = [f.name for f in Lectura._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(ConsolaAmbient)
class ConsolaAmbientAdmin(admin.ModelAdmin):
    list_display = ("device_id", "nombre", "estacion", "ip_origen",
                    "software", "ultimo_reporte", "activa")
    list_filter = ("activa",)
    search_fields = ("device_id", "nombre")
