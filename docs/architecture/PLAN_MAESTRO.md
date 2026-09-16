# Plan Maestro: Traductor PDF (V1 Local y Portafolio)

## 1. Resumen Ejecutivo, Alcance y Exclusiones
El objetivo de **Traductor PDF V1** es ser una aplicación de escritorio local para abrir PDFs en inglés, traducir regiones mediante Ollama asíncrono y exportar el resultado empleando *vector overlay*.
- **Incluido en V1:** Geometría exacta, validación de estado de fondos, edición de regiones, historial por sesión, exportación por proceso independiente.
- **Excluido de V1 (Ampliaciones futuras):** OCR, inpainting real de fondos, cuentas de usuario, servicios en nube, extracción de tablas complejas, batch automático (auto-detección).

## 2. Decisiones Técnicas Aprobadas
- **Renderizado Compartido:** Se utilizará un solo modelo `RegionRenderPlan`. No se usarán dos rutas de wrapping (PyMuPDF vs Qt text engine).
- **Overlay:** V1 ocultará el texto original usando fondo de color uniforme o bloqueará, y luego sobrepondrá la traducción. El inglés original podrá seguir existiendo debajo (extraíble en clipboard).
- **Proyectos y Sesiones:** Una sola instancia abierta por vez con reseteo de historial total al cambiar de archivo.

## 3. Hitos y Tickets Críticos (Roadmap Ejecutable)

### Hito 0: Recuperación y Baseline (Iteración 1)
**Objetivo:** Consolidar una suite de pruebas diagnóstica, sin `PermissionError` de limpieza.

#### Ticket BASE-01: Ownership de recursos en Windows
- **Objetivo:** Resolver el `PermissionError: [WinError 5]` en temp dirs de pytest (H. A22).
- **Dependencia:** Ninguna.
- **Archivos propuestos a modificar:** Clases productivas de persistencia (`src/infrastructure/persistence/database.py`, `repository.py`), adaptador PDF (`src/infrastructure/pdf/adapter.py`) y fixtures (`conftest.py`).
- **Cambios previstos:** Garantizar que los descriptores `.close()` de SQLite y PyMuPDF se llamen en bloques `finally` o managers de contexto, sin borrar explícitamente DBs o PDFs para falsear el test.
- **Criterio Aceptación:** `pytest` no emite `PermissionError` en teardown.

#### Ticket BASE-04: Contratos Históricos
- **Objetivo:** Adaptar las aserciones rotas del contrato HTML/Unicode (H. A15).
- **Cambios previstos:** Corregir los tests afectados, conservando las pruebas de acentos y marcadores.
- **Criterio Aceptación:** `pytest` informa de los verdaderos 30 fallos funcionales sin "errors" de recolección ni de teardown. **No se exige 100% verde.**

---

### Hito 1: Geometría y Causa de Errores (Iteración 2)
#### Ticket SAFE-01: Causas Tipadas en Preflight
- **Objetivo (A05):** El planificador de layout retorna status (OVERFLOW, COMPLEX_BACKGROUND, UNKNOWN) por región en un objeto; el UI lo procesa.
- **Dependencias:** BASE-01.
- **Archivos propuestos:** `region_render_spec_planner.py`, `prepare_pdf_export_use_case.py`.
- **Criterio Aceptación:** Test `test_preflight_overflow` pasa detectando `OVERFLOW` explícitamente y reportando el ID de región.

#### Ticket SAFE-02: Sistema Geométrico Canónico
- **Objetivo (A03):** Manejar CropBox y rotaciones sin desfases de offsets. 
- **Cambios previstos:** Estandarizar la transformación de coordenadas.
- **Criterio Aceptación:** Extracción con matriz de rotaciones 0,90,180,270 y CropBox desplazado coinciden en texto extraído sin cortes.

---

### Hito 2: Fondos y Prevención de Daño (Iteración 3)
#### Ticket SAFE-03: Texto Oscuro y Fondos
- **Objetivo (A01):** Transmitir color de fuente resuelta al spec exportador.
- **Criterio Aceptación:** El fixture `dark_source.pdf` con texto blanco devuelve un PDF donde la traducción (blanca) es visible sobre el rectángulo negro subyacente.

#### Ticket SAFE-04: Resguardo de Objetos Gráficos
- **Objetivo (A02):** Si el bbox del texto solapa o cruza una línea o imagen, NO devolver `UNIFORM_COLOR`. Retornar `COMPLEX_BACKGROUND` y bloquear exportación de esa región (en V1).
- **Criterio Aceptación:** El fixture `hidden_graphic.pdf` retorna falso y el preflight lo bloquea antes de exportar.

#### Ticket SAFE-05: Región Fija
- **Objetivo (A04):** Deshabilitar expansión implícita geométrica (`FIXED_REGION`).
- **Criterio Aceptación:** En `tight_box.pdf`, el área alterada final debe ser matemáticamente <= área de selección.

---

*(Tickets RENDER, DATA, TRANS, PERF y RELEASE se detallarán en próximas extensiones una vez que estos primeros pilares logren estabilidad sin fallos).*
