# -*- coding: utf-8 -*-
"""URLs del proyecto."""
from django.contrib import admin
from django.urls import path

from estaciones import views
from estaciones import views_ambient
from estaciones.api import ambient_vistas, endpoints

urlpatterns = [
    path('admin/', admin.site.urls),

    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Panel Ambient (modulo aislado, estacion 99)
    path('ambient/', views_ambient.ambient, name='ambient'),

    # API de consulta (alimenta las graficas)
    path('api/v1/estaciones/ultima/', views.api_ultima, name='api_ultima'),
    path('api/v1/estaciones/serie/', views.api_serie, name='api_serie'),
    path('api/v1/estaciones/pronostico/', views.api_pronostico,
         name='api_pronostico'),
    path('api/v1/estaciones/historial/', views.api_historial,
         name='api_historial'),

    # Endpoint de recepcion: aqui POSTean las estaciones
    path('api/v1/estaciones/datos/', endpoints.recibir_datos,
         name='api_recibir_datos'),

    # Receptor Ambient Weather (protocolo Wunderground, estacion 99)
    path('weatherstation/updateweatherstation.php',
         ambient_vistas.ambient_recibir, name='ambient_recibir'),
    path('api/v1/ambient/consolas/',
         ambient_vistas.ambient_consolas, name='ambient_consolas'),
    path('api/v1/ambient/ultima/',
         ambient_vistas.ambient_ultima, name='ambient_ultima'),
    path('api/v1/ambient/serie/',
         ambient_vistas.ambient_serie, name='ambient_serie'),
    path('api/v1/ambient/pronostico/',
         ambient_vistas.ambient_pronostico, name='ambient_pronostico'),
]
