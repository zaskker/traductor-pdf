# 005 - PDF Coordinate Mapping

## Context
El sistema requiere mapear selecciones visuales del usuario (en píxeles de pantalla) a coordenadas nativas del PDF para poder aislar regiones de texto e imagen con precisión matemática. 

El problema radica en que intervienen tres espacios de coordenadas distintos:
1. **Viewport / Scene (Qt)**: Coordenadas flotantes visuales afectadas por el zoom y el pan (scroll) interactivo del usuario.
2. **Rendered Pixels**: Coordenadas de la imagen rasterizada devuelta por PyMuPDF, afectadas por un `render_scale` inicial de alta definición.
3. **PDF Native**: Las coordenadas puras lógicas del documento (usualmente expresadas en puntos, sin rotación).

Si la interfaz de usuario calculara manualmente las transformaciones dividiendo por el nivel de zoom, se perdería precisión o fallaría en PDFs complejos con rotaciones u orígenes distintos a `(0, 0)`.

## Decision
Se ha decidido implementar un puerto neutro `IPdfCoordinateMapper` para orquestar la conversión bidireccional entre **Rendered Pixels** y **PDF Native Coordinates**, con las siguientes características:

* **PyMuPDF Mapping Encapsulado**: El adapter de infraestructura `PyMuPDFCoordinateMapper` utiliza `fitz.Matrix` (y su inversa `~matrix`) para realizar la transformación puramente matemática. 
* **Matriz Exacta**: La matriz productiva que conecta el PDF nativo (unrotated) con el Pixmap se construye explícitamente en el Adapter usando la fórmula: `translation(-cropbox) * rotation_matrix * scale_matrix`. Esto garantiza precisión matemática real para páginas rotadas o con offsets de CropBox.
* **Qt Mapping Delegado a la UI**: El widget `PdfViewWidget` es el único responsable de llevar coordenadas del Viewport a la Scene, y de la Scene a los Rendered Pixels utilizando las utilidades de Qt (`mapToScene`, `mapFromScene`).
* **Mapeo de Esquinas**: Para convertir rectángulos lógicos, se prohíbe el uso de `boundingRect()` de Qt, dado que expande la caja limítrofe por redondeos (0.64 pt de error comprobado). En su lugar, el mapper transforma independientemente los 4 puntos del rectángulo (top-left, top-right, bottom-left, bottom-right) y reconstruye la nueva caja limitante (`min_x`, `max_x`, etc.).
* **Uso exclusivo de Floats**: Se evitan los enteros prematuros para preservar precisión sub-píxel.
* **DPI Manual Omitido**: Se comprobó que el comportamiento por defecto de PySide6 absorbe el Device Pixel Ratio para nuestro flujo estándar (DPR 1.0 verificado).

## Evidence
Estas decisiones provienen directamente de los resultados experimentales de la Fase 0.5 (Technical Validation Spikes) y las correcciones de Fase 2. Se construyó un Integration Test real (con rotación de 90 grados y CropBox con offset de 50,100) que comprobó que mapear a través de la matriz compuesta reduce el error matemático a `< 1e-4 pt`.

## Consequences
**Positivas:**
* La UI se simplifica y no necesita conocimiento sobre el estándar PDF.
* Las regiones seleccionadas coinciden de forma exacta con la posición real del texto nativo subyacente, incluso para páginas rotadas (90, 180, 270) o con offsets de CropBox (evidencia provista por `test_adapter_rotated_and_cropped_mapping`).
* Domain, Application y UI no dependen de `fitz`. Infrastructure encapsula la dependencia de PyMuPDF.

**Limitaciones/Pendientes:**
* `DevicePixelRatio > 1.0` (Monitores escalados como 150%) sigue pendiente de verificación formal (STILL UNVERIFIED).
* Qt discretiza obligatoriamente ciertos mappings visuales intermedios a pixeles enteros al interactuar con las Scrollbars/Viewport, lo cual inyecta un error de cuantización invariable (~0.25pt visual), el cual es aceptable para UI interactiva.
