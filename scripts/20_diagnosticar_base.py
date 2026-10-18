# -*- coding: utf-8 -*-
"""Diagnostica que fechas quedaron en la base por estacion."""
import os
import sys

sys.path.insert(0, r"C:\Users\esteb\OneDrive\Desktop\Est Campus Unal")

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "est_campus.settings")
django.setup()

from django.utils import timezone  # noqa: E402

from estaciones.models import Estacion, Lectura  # noqa: E402

for est in Estacion.objects.order_by("codigo"):
    q = Lectura.objects.filter(estacion=est)
    total = q.count()
    print(f"estacion {est.codigo}: {total:,} lecturas")
    if not total:
        continue
    primera = timezone.localtime(q.order_by("timestamp").first().timestamp)
    ultima = timezone.localtime(q.order_by("-timestamp").first().timestamp)
    print(f"  desde {primera}  hasta {ultima}")
