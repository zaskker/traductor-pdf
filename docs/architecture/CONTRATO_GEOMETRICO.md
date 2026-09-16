# Contrato Geométrico

## 1. Espacios de Coordenadas

1. **Espacio Interno del PDF (MediaBox/CropBox no rotados)**
   - Origen: Puede no ser (0,0). Depende de la definición de `MediaBox` o `CropBox` en el archivo PDF.
   - Ejes: Históricamente en PDF puro, Y crece hacia arriba.
   - Unidades: Puntos tipográficos (1/72 pulgada).
   - Rotación: Ninguna (0 grados).

2. **Espacio PyMuPDF (`page.rect`) - Espacio de Dominio**
   - Origen: **Siempre (0, 0)** en la esquina superior izquierda de la vista recortada y rotada.
   - Ejes: X crece a la derecha, Y crece hacia abajo.
   - Unidades: Puntos tipográficos (1/72 pulgada).
   - Rotación: Ya incorpora la rotación de la página (`page.rotation`) y el recorte (`CropBox`).
   - Aplicabilidad: Las funciones principales de PyMuPDF como `get_text()`, `insert_text()`, y la generación de imágenes (`get_pixmap()`) operan **nativamente en este espacio**.
   - **Contrato:** La aplicación de dominio (e.g. `Rect` guardados en base de datos) usa este espacio.

3. **Espacio Raster (Píxeles de Pantalla)**
   - Origen: (0, 0) esquina superior izquierda del área renderizada.
   - Ejes: X a la derecha, Y hacia abajo.
   - Unidades: Píxeles físicos de pantalla.
   - Relación con Espacio PyMuPDF: Píxeles = Espacio PyMuPDF * `render_scale`.
   
4. **Espacio de Escena (QGraphicsScene)**
   - Origen: Coincide con el centro (0,0) u origen top-left dependiendo del layout. En nuestra aplicación, la vista proyecta los items en una escena, pero la selección se mapea al tamaño del pixmap local de la página, por lo que es equivalente al Espacio Raster más un desplazamiento (viewport offset).

## 2. Responsabilidad de Conversión

- **Mapper UI -> Dominio (`PyMuPDFCoordinateMapper`):** Convierte de Espacio Raster (Píxeles) a Espacio PyMuPDF (`page.rect`). Debido a que PyMuPDF ya absorbió el CropBox y la Rotación en `page.rect`, la única transformación matemática real necesaria es la **escala** (`render_scale`). **No** se deben re-aplicar transformaciones de `cropbox` ni `rotation_matrix` para mapear selecciones de pantalla a PDF.
- **Extractor/Inspector:** Utiliza el Espacio PyMuPDF directamente, ya que `get_text` devuelve coordenadas basadas en `page.rect`.
- **Exportador (`VectorFormExporter`):** Inserta texto sobre el mismo documento original usando APIs que interpretan las posiciones relativas a `page.rect`. Nuevamente, no se requiere des-rotar coordenadas si no se manipulan directamente objetos vectoriales crudos sin la API de alto nivel de PyMuPDF.

## 3. Compatibilidad
- Las coordenadas persistidas asumen estar en el Espacio PyMuPDF (`page.rect`).
- Si anteriormente se agregaba una traslación errónea (e.g. sumar `CropBox` o aplicar matriz de rotación innecesariamente), los proyectos guardados con CropBoxes desplazados podrían tener coordenadas desviadas en disco.
- Esta iteración corrige el contrato a futuro, y cualquier migración de base de datos personal queda fuera del alcance (conforme a las instrucciones restrictivas de SAFE-02).
