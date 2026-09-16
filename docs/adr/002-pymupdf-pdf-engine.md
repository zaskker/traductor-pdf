# 002 - PyMuPDF PDF Engine

**Status:** Aprobado (Fase 0)

**Context:**
Necesitamos renderizar documentos PDF a imágenes de forma eficiente para mostrarlos en la UI de Qt, extraer texto nativo y su estilo (fuentes, tamaños) basándonos en selecciones geométricas precisas, e inyectar nuevas capas o redacciones en el documento al exportar, preservando la calidad e integridad visual del resto de la página.

**Decision:**
Utilizaremos **PyMuPDF (fitz)** como nuestro motor de PDF en la capa de `Infrastructure`.

**Consequences:**
* **Positivo:** PyMuPDF es uno de los wrappers más rápidos y completos de C/C++ en Python para manejo de PDF.
* **Positivo:** Soporta extracción de texto enriquecido (mediante el comando `get_text("dict")`) y transformaciones matemáticas precisas mediante matrices.
* **Positivo:** Permite renderizar y obtener `Pixmap` que se pueden inyectar en `QImage` eficientemente, además de soportar anotaciones y redaction.
* **Negativo:** Su API nativa es a veces imperativa o "pythónica" al estilo C antiguo, lo cual obligará a nuestra capa de infraestructura a ser cuidadosa para aislar este comportamiento del resto de la aplicación.
