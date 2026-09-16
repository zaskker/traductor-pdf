# Traductor PDF

Aplicación de escritorio para Windows desarrollada en Python/PySide6 que permite seleccionar regiones de documentos PDF, traducirlas mediante modelos locales de Ollama y exportar un nuevo PDF conservando el diseño mediante un sistema Safe Overlay.

## Características

- Selección manual de regiones en un visor PDF integrado.
- Traducción local offline utilizando Ollama (llama3.2:3b, o personalizable).
- Edición de traducciones antes de ser confirmadas.
- Preview visual in-situ del resultado directamente en el documento.
- Glossary versionado para estandarización terminológica.
- Flujo de Review/Approval para control de calidad.
- Translation Memory local por proyecto.
- Batch translation para procesar múltiples regiones simultáneamente.
- Persistencia local y atómica mediante SQLite.
- Exportación aislada (worker) conservando el layout.
- Safe Overlay para posicionar texto traducido con precisión geométrica.
- Validaciones estructurales de salida LLM.
- Corrective retry acotado.
- Arquitectura hardened para uso en Windows.

## Stack Tecnológico

- Python 3.12+
- PySide6 (UI)
- PyMuPDF (PDF Engine)
- SQLite (Persistencia)
- Ollama (LLM Engine)
- PyInstaller (Empaquetado)
- pytest / pytest-qt (Testing)

## Estado del proyecto

Version: `1.0.0-rc1`

Tests: `563 passed / 4 skipped`

## Arquitectura

El proyecto está diseñado bajo principios de Clean Architecture y MVVM (Model-View-ViewModel):
- **Domain:** Modelos puros, interfaces y reglas de negocio.
- **Application:** Casos de uso y coordinadores.
- **Infrastructure:** Adapters (PyMuPDF, SQLite, Ollama).
- **Presentation:** ViewModels (UI State) y Componentes PySide6.
- **Workers:** Exportación aislada mediante un proceso secundario independiente.

## Requisitos

- Windows x64.
- Ollama instalado y corriendo (por defecto utiliza `llama3.2:3b`).
- Para ejecutar desde código fuente: Python 3.12+.

## Instalación para usuario

1. Descargar el archivo `.zip` de la última [Release en GitHub].
2. Extraer el contenido en una carpeta local.
3. Ejecutar `TraductorPDF.exe`.
4. Asegurarse de tener Ollama disponible con un modelo válido.

## Configuración Ollama

Para ejecutar el traductor, debes tener el servicio de Ollama activo en segundo plano.
Por defecto, el sistema utilizará el modelo `llama3.2:3b`.
Instálalo ejecutando:
`ollama run llama3.2:3b`

## Uso Básico

1. Abrir un documento PDF.
2. Seleccionar una región de texto.
3. Traducir (la petición se enviará a Ollama).
4. Activar Preview para ver cómo quedará la traducción en el PDF.
5. Revisar y Aprobar la traducción.
6. Exportar el documento.

*Nota: Puedes traducir varias regiones juntas utilizando la funcionalidad Batch.*

## Safe Overlay / Limitaciones

V1 utiliza un sistema de **Safe Overlay** para la exportación. Esto implica ciertas limitaciones conocidas:
- El texto original en inglés permanece seleccionable/buscable por debajo de la traducción visual (Overlay).
- No incluye funcionalidad OCR (reconocimiento óptico de caracteres).
- No incluye inpainting (borrado inteligente de fondos complejos).
- Los PDFs protegidos por contraseña no están soportados.
- El texto y fondos extremadamente complejos pueden impedir una superposición 100% limpia.
- El rendimiento general y la precisión dependen del modelo local utilizado y el hardware disponible.

## Desarrollo Local

Para desarrolladores que deseen compilar y ejecutar el proyecto:

```bash
# Crear entorno virtual
python -m venv .venv
.\.venv\Scripts\activate

# Instalar dependencias
pip install -e ".[dev]"

# Ejecutar tests
python -m pytest tests -q

# Ejecutar la aplicación
python -m src.main
```

## Pruebas (Testing)

El proyecto cuenta con una robusta suite de pruebas que incluye pruebas unitarias y de integración sobre persistencia, modelo de dominio, UI (Qt), Worker processes, Glossary y Batch.

Para correr la suite localmente:
```bash
python -m pytest tests -q --basetemp=tests/tmp
```
*Current Baseline: 563 passed, 4 skipped.*

## Build (Empaquetado)

Para generar el ejecutable (Release Candidate) en Windows, ejecuta el script de powershell provisto (requiere PyInstaller instalado en el entorno virtual).

```powershell
.\build_release.ps1
```
El build utiliza el modo OneDir para mejor inicialización y debugging.

## License

MIT License.
