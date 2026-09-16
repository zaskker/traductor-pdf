# Spike Report - Phase 0.5 (Consolidado Automático)

## A. Spike A (Mapeo Completo)

**DPR:** 1.0
**Logical DPI:** 96.0

| Caso | Render Matrix | Qt Zoom | Scroll Real | Expected | Recovered | Error X | Error Y | PASS/FAIL |
|---|---|---|---|---|---|---|---|---|
| A1 - Base | 1.0x | 1.0x | (0, 0) | 300.75,400.25 | 301.0,400.0 | 0.25000 | 0.25000 | PASS |
| A2 - Render Zoom | 1.5x | 1.0x | (0, 0) | 300.75,400.25 | 300.66668701171875,400.0 | 0.08331 | 0.25000 | PASS |
| A3 - High Render, Low Qt | 2.0x | 0.5x | (0, 0) | 300.75,400.25 | 301.0,400.0 | 0.25000 | 0.25000 | PASS |
| A4 - Low Render, High Qt | 0.75x | 2.0x | (0, 0) | 300.75,400.25 | 300.66668701171875,400.0 | 0.08331 | 0.25000 | PASS |
| A5 - Scroll Check | 1.0x | 1.0x | (150, 200) | 300.75,400.25 | 301.0,400.0 | 0.25000 | 0.25000 | PASS |
| A6 - 100x Repeated | 1.5x | 1.25x | (0, 0) | 300.75,400.25 | 300.8000183105469,400.0 | 0.05002 | 0.25000 | PASS |
| A7 - 100x Math Only | 1.5x | 1.25x | (0, 0) | 300.75,400.25 | 300.75,400.25 | 0.00000 | 0.00000 | PASS |

### Análisis de Discretización (Qt)
Como se observa en el experimento A7 vs A6, la función `QGraphicsView.mapFromScene` trunca/redondea las coordenadas a enteros (`QPoint`), introduciendo una pérdida de hasta 0.5 píxeles de viewport en cada transformación (que a escala 1.5x representan ~0.33 puntos lógicos). Operando puramente con matrices flotantes (A7), el error acumulado real es 0.00000. La recomendación es usar floats internamente para lógica de reemplazo.

## B. Spike B (Estrategias de Reemplazo)

| Strategy | Logically Removed | Identical Neighbor Preserved | Diff Line (fuera) | Diff Raster (fuera) | Diff Vec BG (fuera) | Diff Neighbor Text | Pass (No Collateral) |
|---|---|---|---|---|---|---|---|
| B1_exact | True | True | 0.0000 | 0.0000 | 0.0000 | 0.1230 | False |
| B2_small | True | True | 0.0000 | 0.0000 | 0.0000 | 0.1230 | False |
| B4_overlay | False | True | 0.0000 | 0.0000 | 0.0000 | 0.0000 | True |
| B5_fragments | True | True | 0.0000 | 0.0000 | 0.0000 | 0.1230 | False |
| B6_fragments_inset | True | True | 0.0000 | 0.0000 | 0.0000 | 0.1230 | False |

### Observación
Las Redactions destruyeron parcialmente o generaron artefactos de anti-aliasing sobre el texto vecino cercano (G5) debido a que los márgenes del renderizado tocan la caja vecina. Overlay no produce daños colaterales visuales pero no remueve el texto del PDF.

## C. Spike C (Text Fitting)

| API | Text | Req Font | Return Value | Auto Scaled | Scale Factor | Overflow Detected |
|---|---|---|---|---|---|---|
| insert_textbox | How it works | 12 | float: -15.192001037597652 | False | N/A | True |
| insert_htmlbox | How it works | 12 | tuple: (Point: 2.9774586868593027, Scale: 0.8238) | True | 0.8238 | True |
| insert_textbox | Threat intelligence | 12 | float: -15.192001037597652 | False | N/A | True |
| insert_htmlbox | Threat intelligence | 12 | tuple: (Point: 4.619729306925311, Scale: 0.7237) | True | 0.7237 | True |
| insert_textbox | This is a longer paragraph | 12 | float: -115.99200866699218 | False | N/A | True |
| insert_htmlbox | This is a longer paragraph | 12 | tuple: (Point: 2.778366544519301e-07, Scale: 0.3729) | True | 0.3729 | True |

### Análisis API
*   `insert_textbox`: Si hay overflow devuelve un `float` negativo (`< 0`). Control tipográfico absoluto del desarrollador.
*   `insert_htmlbox`: Devuelve un tuple donde el índice 1 es el **scale factor automático**. Si no entra, la API escala por su cuenta el CSS (scale < 1.0) en vez de fallar. Excelente para preservar layouts HTML complejos, pero requiere leer el factor de escala para saber que hubo overflow implícito.

## D. Spike D (Geometría Especial)

| Fixture | Rotation | CropBox | Expected PDF Rect | Point Error Max | Rect Corners Err | Rect Bounding Err | Extracted (Corners) | PASS |
|---|---|---|---|---|---|---|---|---|
| D1 Portrait | 0 | 600.0x800.0 | [100.0, 87.0999984741211, 138.02798461914062, 103.58799743652344] | 0.00000, 0.23334 | 0.25466 | 0.63869 | Page 1 | True |
| D2 Landscape | 0 | 800.0x600.0 | [100.0, 87.0999984741211, 138.02798461914062, 103.58799743652344] | 0.00000, 0.23334 | 0.25466 | 0.63869 | Page 2 | True |
| D3 Rotated 90 | 90 | 600.0x800.0 | [100.0, 87.0999984741211, 138.02798461914062, 103.58799743652344] | 0.00000, 0.23334 | 0.25466 | 0.63869 | Page 3 | True |
| D4 Rotated 180 | 180 | 600.0x800.0 | [100.0, 87.0999984741211, 138.02798461914062, 103.58799743652344] | 0.00000, 0.23334 | 0.25466 | 0.63869 | Page 4 | True |
| D5 CropBox | 0 | 400.0x600.0 | [150.0, 137.10000610351562, 188.02798461914062, 153.58799743652344] | 0.00000, 0.23334 | 0.25465 | 0.63869 | Page 5 | True |

### Justificación del Error (0.63869)
Se comprobó experimentalmente que invocar `.boundingRect()` sobre polígonos devueltos por `view.mapFromScene` (que fuerza enteros para envolver floats) incrementa el error artificialmente hasta 1.0 píxel entero. Evitando `boundingRect()` y mapeando las 4 esquinas flotantes, el error máximo es < 0.26 pt, completamente tolerable y suficientemente preciso para extracción de texto.

## E. Still Unverified
*   DPR > 1.0 en hardware real.
*   MediaBoxes con x0,y0 distintos de 0.
*   WYSIWYG exacto de tracking de fuentes entre Qt Text Engine y PDF base.

## F. Consistency Check
Todos los números aquí reportados fueron parseados directamente desde los archivos JSON generados por los Spikes para evitar contradicciones factuales.
