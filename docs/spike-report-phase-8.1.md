# Spike Report 8.1 - PyMuPDF Rendered Region Preview

## 1. Root Cause Horizontal Confirmado
La discrepancia tipográfica observada (ej. espaciados irregulares en palabras como "navegador" o "retraso") se debe a que `insert_textbox` de PyMuPDF utiliza métricas de `Base-14 Helvetica` (o su equivalente estándar embebida) junto con un layout interno de kerning y word-spacing, mientras que la UI delega la pintura final a `QPainter.drawText` utilizando la fuente `Arial` nativa del sistema (con sus propias métricas) y aplicando un truncamiento a entero (`int(layout.font_size)`). Esto provoca que la distribución horizontal calculada por PyMuPDF (autoridad) y la pintada por Qt (presentación) difieran, generando colisiones visuales o espacios erráticos.

## 2. Resultado A1 (Qt int + Arial)
El baseline actual de producción fue reproducido en el spike (`A1_Qt_int_*.png`). Presenta las distorsiones esperadas en el espaciado intra-palabra debido a la pérdida de precisión sub-pixel (float truncado) y al reemplazo de fuente subyacente. Los glyph advances de Arial sencillamente no encajan a la perfección con la caja delimitadora originalmente inferida por PyMuPDF.

## 3. Resultado A2 (Qt float + Helvetica)
El escenario A2 (`A2_Qt_float_*.png`) mejoró marginalmente al utilizar `setPointSizeF(font_size)` para retener el float original y solicitar `Helvetica` (que Qt resuelve al closest match disponible en el OS). Aún así, la rasterización de Qt difiere sutilmente del engine de PyMuPDF. Se comprobó empíricamente que PyMuPDF tiene su propia mecánica de text-rendering que no es 100% intercambiable (wysiwyg) con un simple `drawText`.

## 4. Resultado B (PyMuPDF Raster)
La aproximación B (`B_PyMuPDF_*.png`) generó un `get_pixmap()` directamente desde la página temporal donde se ejecutó `insert_textbox`. 
- Elimina completamente los artefactos de espaciado.
- Reproduce **exactamente** la disposición de caja y métricas que PyMuPDF usó para calcular el FIT.
- La salida tipográfica es inmaculada comparada con Qt porque el mismo engine que midió, dibujó.

## 5. Comparación Visual
Al examinar las imágenes generadas, las palabras problemáticas del QA ("navegador", "retraso", "proxies", "información") aparecen perfectamente formateadas en el raster de PyMuPDF, mientras que en A1 se ven apretadas o irregularmente distribuidas. Esto evidencia que el render native-PDF es la única forma robusta de garantizar WYSIWYG absoluto con respecto a la fase de export.

## 6. Performance
Se ejecutó un benchmark aislando la generación de la página, `insert_textbox` y `get_pixmap(matrix)` sobre la región local:

**Scale 1.0x:**
- 1 region: ~2.3 ms
- 10 regions: ~23 ms
- 25 regions: ~56 ms

**Scale 2.0x:**
- 1 region: ~2.4 ms
- 10 regions: ~24 ms
- 25 regions: ~60 ms

El overhead de rasterizar es **diminuto**, variando apenas 1 ms al duplicar la escala para regiones de texto estándar. En total, renderizar dinámicamente 25 regiones simultáneas tomaría ~60 milisegundos en el hilo actual.

## 7. Render Scale Recomendado
Se recomienda un **Render Scale de 2.0x** estático (o alternativamente coincidente con el DPI base de Qt, como el `devicePixelRatio`). 
Un scale de 2.0x proporciona un oversampling perfecto para que Qt escale el pixmap en la escena (manteniendo la nitidez con `SmoothTransformation` cuando se hace zoom) sin casi penalización de performance respecto a 1.0x (~2.4ms por región).

## 8. Arquitectura Recomendada
**Gana decididamente: PyMuPDF raster preview.**
Tratar de forzar a Qt a "emular" el kerning y spacing de PyMuPDF es propenso a errores frágiles y hacky. Rasterizar una vez en PyMuPDF asegura la regla de oro: el Preview mostrará **exactamente** lo que se quemará en el PDF exportado (Wysiwyg).

## 9. Port/DTO Propuesto
Para mantener limpio `TextLayoutResult` y no inyectarle bytes pesados que rompan el caché tipográfico o confundan al domain puro de layout:

Propongo un Port separado, por ejemplo:
```python
class ITextPreviewRenderer(ABC):
    @abstractmethod
    def render_preview(self, input_data: TextLayoutInput, font_size: float) -> RenderedTextPreview:
        pass
```

Y un DTO neutral:
```python
@dataclass(frozen=True)
class RenderedTextPreview:
    samples: bytes
    width: int
    height: int
    channels: int
```
Este `RenderedTextPreview` vive únicamente en capa de UI/Application y Qt puede instanciar un `QImage` seguro y barato desde sus `samples`. Se puede cacheados separadamente si la performance se vuelve tema.

## 10. Archivos productivos que cambiarían después
- `src/application/ports/text_preview_renderer.py` (Nuevo)
- `src/domain/value_objects/layout.py` (Nuevo DTO `RenderedTextPreview`)
- `src/infrastructure/pdf/preview_renderer.py` (Implementación de PyMuPDF `get_pixmap()`)
- `src/ui/viewmodels/pdf_viewer_viewmodel.py` (Nuevo método/estado transitorio para buscar la imagen del preview)
- `src/ui/components/pdf_view_widget.py` (Inyectar el nuevo renderer callback)
- `src/ui/components/translation_preview_item.py` (Refactorizado para recibir un QImage/pixmap y dibujarlo, en vez de drawText).

## 11. Confirmación
Confirmo estrictamente: **FASE 9 NO iniciada**.
El spike se corrió en un directorio aislado (`spikes/text_preview_rendering/`) y producción no fue alterada. Quedo detenido aguardando directivas.
