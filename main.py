import os
import sys
from pathlib import Path

# Añadir raíz del proyecto al path de Python
sys.path.insert(0, str(Path(__file__).parent))

from est_campus.wsgi import application

# La aplicación WSGI/ASGI es la entrada al servidor
