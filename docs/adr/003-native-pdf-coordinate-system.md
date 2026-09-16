# 003 - Native PDF Coordinate System

**Status:** Aprobado (Fase 0)

**Context:**
Una selección dibujada en pantalla (UI) está fuertemente atada al zoom actual, el DPI del monitor (`devicePixelRatio`), desplazamientos de scroll e incluso rotaciones de página aplicadas en la previsualización. Si guardamos estas coordenadas "visuales", la selección dejará de apuntar al texto correcto si cambia la configuración de visualización o se abre el proyecto en otro monitor.

**Decision:**
Todo el sistema (`Domain`, base de datos y memoria) almacenará y operará exclusivamente utilizando **coordenadas nativas del PDF (puntos/points)**. PyMuPDF define un punto como 1/72 de pulgada con el origen (0,0) en la esquina superior izquierda (considerando internamente CropBox y rotaciones).
Las transformaciones hacia y desde coordenadas de píxeles en pantalla se delegarán estrictamente a las funciones matemáticas de Qt (`QTransform`, `mapToScene`, `mapFromScene`) combinadas con la inversa de `fitz.Matrix`. 
Está estrictamente prohibido introducir fórmulas multiplicadoras manuales (ej. `x * zoom * (DPI/72)`) si existen abstracciones nativas disponibles en Qt.

**Consequences:**
* **Positivo:** Precisión absoluta sin importar el nivel de zoom o monitor.
* **Positivo:** Coherencia garantizada a largo plazo en la persistencia.
* **Negativo:** Mayor complejidad en la implementación del binding entre UI e Infraestructura, especialmente al manejar HiDPI y rotaciones, requiriendo testing exhaustivo.
