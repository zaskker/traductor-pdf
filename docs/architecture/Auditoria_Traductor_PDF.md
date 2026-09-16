# Auditoría técnica y recuperación del proyecto Traductor PDF

**Fecha:** 5 de septiembre de 2026.  
**Objeto:** código y documentación de `Traductor.zip`.  
**Tipo de trabajo:** revisión de arquitectura y flujos, ejecución de pruebas disponibles y reproducciones dirigidas; no modificación del proyecto original.

## 1. Conclusión ejecutiva

No hace falta empezar de cero. Hay un MVP avanzado con separación por capas, persistencia, traducción asíncrona y exportación aislada en un proceso. Pero el estado real no es el del resumen: las fases 6 y 8 ya tienen implementación y conexión al arranque. El código incluye una refactorización de layout compartido, bloques y soporte Unicode que todavía no quedó cerrada en todos sus contratos.

La prioridad no es agregar batch o inpainting inmediatamente. Primero hay que impedir resultados visualmente incorrectos que el programa acepta como exitosos, estabilizar geometría y sesiones, y recuperar una base verificable de pruebas. El objetivo defendible es una versión 1.0 completa **dentro de un alcance de PDFs y estilos explícito**, no una promesa de preservar absolutamente cualquier PDF.

No asigno un porcentaje de avance: la cantidad de archivos o de funciones no mide el riesgo restante, y falta validar Windows, modelos reales y un corpus representativo del usuario.

## 2. Alcance, método y límites

El inventario incluye **85 archivos Python en src (9.110 líneas)** y **67 en tests (9.989 líneas)**. Hice una revisión dirigida de los caminos críticos: apertura/selección, extracción, traducción, guardado, layout, preview, preflight, exportador, IPC y sesiones UI. La documentación antigua se usó como intención de diseño, no como prueba de funcionamiento.

El ZIP se extrajo sin reutilizar ejecutables de su entorno virtual Windows. Las pruebas se ejecutaron en Linux con Python 3.13.5 y PyMuPDF 1.26.7, además de la dependencia de fuentes compatible disponible en el archivo. Los metadatos de `.venv` del ZIP indican PyMuPDF 1.28.2, PySide6 6.11.2, pytest 9.1.1 y ruff 0.16.4; no reproduje ese entorno exacto. Por ello, los casos PDF deben volver a correrse en las versiones objetivo antes de cerrar cada incidencia. No asumí que todo comportamiento dependiente de versión fuera idéntico.

PySide6 y ruff no estuvieron disponibles para ejecución. No se validó manualmente la GUI de Windows, no se construyó un instalador y no se conectó a un Ollama real. Las conclusiones de UI están rotuladas como revisión estática, no como interacciones observadas. Los PDFs de regresión son sintéticos, creados para aislar defectos; no constituyen un benchmark de todos los documentos posibles.

**Evidencia:** `pytest_tests_only.log/.xml`, `probes/results.json`, `worker_result.json`, scripts reproducibles y PDFs/capturas en el paquete de evidencias. Las referencias `src/...:línea` apuntan a esta copia auditada y pueden cambiar tras editarla.

## 3. Estado real por fase

| Componente | Estado observado | Trabajo restante principal |
|---|---|---|
| Fundaciones y capas | Implementadas | Recuperar baseline reproducible y resolver deuda entre contratos |
| Visor/navegación/zoom | Implementados | QA real Windows y rendimiento con documentos grandes |
| Selección y coordenadas | Implementadas, con defecto reproducido | Unificar CropBox, rotación y espacio de extracción/exportación |
| Extracción nativa | Implementada | Estructura semántica, orden de lectura y casos complejos; OCR aparte |
| SQLite/edición/Undo | Implementados parcialmente consistentes | Metadatos, reubicación, cambio seguro de sesión y backups |
| Ollama asíncrono | Integrado | Calidad real, cancelación, errores, trazabilidad y revisión |
| Fase 6: fitting | Existe y está conectado | Estilos, límites de geometría, semántica de errores y legibilidad |
| Fase 7: batch | No encontré un flujo completo | Cola persistente, selección múltiple, pausa/reanudación |
| Fase 8: preview PyMuPDF | Existe y está conectado | Paridad comprobada, rotación, diagnósticos y cache |
| Fase 9: exportación | Camino funcional y worker verificado | Bloqueos visuales, modos de reemplazo, errores de proceso |
| Producto distribuible | No acreditado | Empaquetado completo, licencias, instalación limpia y QA de release |

En `src/main.py:31-61` se construyen e inyectan `PyMuPDFTextLayoutEngine`, `PyMuPDFTextPreviewRenderer` y el caso de uso de preview. La ruta actual compartida usa `HtmlTextRenderer`/`insert_htmlbox`, no se limita a `QPainter.drawText` ni al spike antiguo basado solo en `insert_textbox`.

## 4. Resultados de ejecución

```text
python -m pytest tests -q --continue-on-collection-errors
335 passed, 31 failed, 1 skipped, 17 errors
```

Los 17 errores de colección proceden de la falta de PySide6. El test saltado necesita Ollama real. Los 31 fallos se distribuyen en 12 del contrato HTML, 17 del contrato Unicode, 1 del error de preflight y 1 de representación de bloques traducidos. Esto no significa 31 funcionalidades independientes rotas: muchos son consecuencia del mismo cambio de API. Tampoco significa que se deban borrar los tests o debilitar sus expectativas.

La ejecución sin limitar a `tests` también recoge `spikes/test_...` porque la configuración de `pytest.ini` deja sin efecto la selección pretendida en `pyproject.toml`; agrega tres errores. Hay que tener un único contrato de ejecución.

El **worker de exportación real** ejecutado sin GUI terminó con código 0, emitió READY/STARTED/PROGRESS/COMPLETED, generó un PDF que se vuelve a abrir y mantuvo intacto el SHA-256 de la fuente. Es evidencia positiva del camino normal, no certificación del coordinador Qt ni del EXE.

## 5. Lo que conviene conservar

La separación de entidades, casos de uso, puertos, adaptadores y vistas es aprovechable. También lo son los SourceFragment con geometría/metadata, los comandos de edición con historial, los controles de resultados de traducción obsoletos y la protección de tokens técnicos. No propongo cambiar de lenguaje ni reescribir el proyecto completo.

La exportación ya tiene decisiones correctas: aislamiento por proceso, protocolo JSON versionado, comprobación de fingerprint, archivo temporal en el directorio de destino, verificación posterior y reemplazo atómico. El planificador común de preview/export va en la dirección correcta, pero debe entregar un contrato completo y no perder errores.

El motor Fake se selecciona como modo de desarrollo; el código no implementa el fallback automático descrito en el resumen. Mantener esa distinción explícita es preferible a producir silenciosamente traducciones ficticias.

## 6. Hallazgos detallados

**Prioridades propuestas:** P0 bloquea una salida confiable o amenaza datos de otro proyecto; P1 afecta corrección, recuperación o release; P2 es ampliación, robustez secundaria o herramienta auxiliar. La prioridad no es una puntuación de seguridad informática.

### A01 · P0 · Texto blanco sobre fondo negro se vuelve invisible

**Evidencia:** Reproducido.  
**Ubicación:** `src/application/dtos/export.py:82-107; src/infrastructure/pdf/html_text_renderer.py:68-141`.

Un PDF sintético contiene texto blanco sobre un rectángulo negro. La extracción detecta el texto; el analizador devuelve UNIFORM_COLOR con RGB (0,0,0); el preflight autoriza y el exportador finaliza correctamente. Sin embargo, TEXTO EN ESPANOL se inserta en negro. La traducción está en el PDF pero no se ve. Lo comprobé con PyMuPDF y con una imagen renderizada por Poppler. El original conserva su SHA-256.

**Impacto.** Es un incumplimiento directo del objetivo del producto, no un detalle estético. Un mensaje de exportación exitosa no garantiza una traducción legible.

**Corrección propuesta.** Agregar color de texto y estilo al modelo de renderizado compartido, transmitirlos por IPC y aplicarlos al HTML. Preservar el color original cuando sea apropiado; advertir o bloquear combinaciones no soportadas. Mientras no se corrija, no anunciar soporte general de fondos uniformes de color.

**Aceptación.** El PDF dark_source.pdf debe producir texto visible con contraste adecuado; verificar color de los spans y comparación visual, no solamente presencia de palabras. Repetir con fondo gris, color saturado y texto multicolor.

### A02 · P0 · Un gráfico puede quedar tapado aunque el fondo se declare seguro

**Evidencia:** Reproducido.  
**Ubicación:** `src/infrastructure/pdf/background_analyzer.py:73-160`.

El analizador omite rectángulos completos de SourceFragment al muestrear el fondo. Dibujé una línea azul dentro del bbox del texto: la clasificación resultó UNIFORM_WHITE y la exportación cubrió la línea. El gráfico desaparece visualmente del resultado; el original no se modifica.

**Impacto.** El fail-safe actual no detecta todos los fondos peligrosos. Existe un falso negativo importante precisamente en zonas donde texto y gráficos se superponen.

**Corrección propuesta.** Combinar análisis de objetos PDF con muestreo raster: dibujos, imágenes, líneas y anotaciones relevantes. No tratar todo lo excluido como fondo seguro. Si hay incertidumbre, devolver una causa específica y bloquear la estrategia de relleno opaco. Evaluar retirada selectiva de texto nativo como estrategia separada.

**Aceptación.** Agregar el fixture hidden_graphic_source.pdf y variantes con líneas de tabla, gráficos finos y fondos parcialmente ocluidos. Ningún caso puede aprobarse como uniforme y tapar objetos protegidos.

### A03 · P0 · Las coordenadas fallan con CropBox desplazado

**Evidencia:** Reproducido.  
**Ubicación:** `src/infrastructure/pdf/adapter.py:70-98; src/infrastructure/pdf/source_inspector.py:39-51; src/infrastructure/pdf/vector_form_exporter.py:158-176`.

Con MediaBox 600x600 y CropBox (150,100,450,400), el texto visible tiene bbox aproximado (30,34.95,138.91,54.19). Seleccionar ese texto en coordenadas visibles produce, a través del mapper, un desplazamiento extra de (150,100): la extracción devuelve vacío. Un rectángulo válido para la página visible también puede ser rechazado por el exportador al compararlo con el CropBox en otro espacio.

**Impacto.** El usuario dibuja una caja sobre un texto y el programa selecciona otra zona o no extrae nada. No basta con conservar el valor del CropBox al exportar.

**Corrección propuesta.** Documentar un espacio canónico de coordenadas y convertir únicamente en las fronteras render/UI/PDF. Unificar extracción, obstáculos, preview, validaciones y exportación. No corregir solo una resta: actualmente hay usos incompatibles del origen del CropBox. Revisar las convenciones de PyMuPDF [R1].

**Aceptación.** Pruebas con texto real y puntos de referencia, no solo ida/vuelta de matrices. Matriz de rotaciones 0/90/180/270, CropBox desplazado, escalas 1/2 y selecciones asimétricas; comprobar texto extraído y posición visual final.

### A04 · P0 · La zona de reemplazo se expande sin aprobación

**Evidencia:** Reproducido.  
**Ubicación:** `src/application/services/structured_layout_builder.py:112-151; src/application/services/region_render_spec_planner.py:40-48,143-154`.

Para una fuente de una sola línea, el layout amplía el rectángulo hacia el margen disponible. En una prueba, la selección terminaba en x=230 y el overlay terminó en x=398 sobre una página de 400 puntos. La ampliación ocurre al preparar candidatos, no solo después de demostrar que el texto no cabe.

**Impacto.** Contradice el contrato de modificar solo la región seleccionada y cambia el alcance de los riesgos de fondo y colisión.

**Corrección propuesta.** Definir FIXED_REGION como comportamiento predeterminado. Una estrategia EXPAND_WITH_APPROVAL debe mostrar la geometría propuesta, sus conflictos y requerir aprobación explícita. Incluir obstáculos no textuales. Persistir la decisión geométrica aprobada.

**Aceptación.** Para FIXED_REGION, la geometría y la máscara efectiva de modificación deben estar contenidas en la selección, dentro de una tolerancia documentada. Una traducción corta no debe expandir nada.

### A05 · P1 · Se pierden las causas de error del planificador

**Evidencia:** Reproducido y revisión estática.  
**Ubicación:** `src/application/services/region_render_spec_planner.py:101-106,125-141; src/application/use_cases/prepare_pdf_export_use_case.py:193-200; src/application/use_cases/prepare_region_preview_use_case.py:49-61`.

El planificador descarta con continue regiones complejas/desconocidas y regiones con overflow. El preflight interpreta cualquier diferencia de cantidad como UNKNOWN_BACKGROUND. La prueba test_preflight_overflow falla por este motivo. En preview, la ausencia de un spec devuelve None y el resultado exitoso utiliza un layout FIT ficticio para compatibilidad.

**Impacto.** La interfaz no puede explicar qué región falló ni distinguir un texto largo de un fondo inseguro. Un fallback de dibujo aproximado puede ocultar que no existe una previsualización exportable.

**Corrección propuesta.** Retornar un resultado por región con spec opcional, causas tipadas, page_number, region_id, fit_status y geometría. Conservar OVERFLOW, COMPLEX_BACKGROUND, UNKNOWN_BACKGROUND y causas de fuente/contraste. Un diagnóstico Qt debe rotularse como no exportable; nunca presentarse como WYSIWYG.

**Aceptación.** Cada fallo debe conservar su identidad desde infraestructura hasta el mensaje de UI. El test de overflow debe volver a comprobar OVERFLOW con identificador de región y página; no cambiar la expectativa para legitimar el error genérico.

### A06 · P1 · La confirmación para exportar solo traducciones queda inaccesible

**Evidencia:** Reproducido en el caso de uso y condición de UI.  
**Ubicación:** `src/application/use_cases/prepare_pdf_export_use_case.py:135-156; src/presentation/coordinators/export_ui_coordinator.py:112-142`.

Con una región traducida y una pendiente, el preflight devuelve exportable_regions=0 porque sale antes de evaluar candidatos. El coordinador solo ofrece exportar las traducidas cuando ese contador es mayor que cero. En la prueba, la condición no se cumple; invocar directamente EXPORT_TRANSLATED_ONLY sí permite continuar.

**Impacto.** Un flujo previsto por el roadmap original no queda disponible desde la lógica actual de interfaz.

**Corrección propuesta.** Separar candidates_count de exportable_count y ejecutar las comprobaciones necesarias antes de ofrecer una política parcial. No saltar otros bloqueos al resolver PENDING_REGIONS.

**Aceptación.** Caso integrado con dos regiones: ofrecer la opción, cancelar sin efectos y aceptar exportando exclusivamente la aprobada. Agregar variante donde la traducida además tiene overflow.

### A07 · P1 · Los saltos de línea pueden perderse al convertir texto a HTML

**Evidencia:** Reproducido.  
**Ubicación:** `src/infrastructure/pdf/html_text_renderer.py:51-87`.

Enviar Primera linea, Segunda linea y Tercer parrafo separados por saltos simples y dobles produce una sola línea cuando hay ancho suficiente. El texto se escapa correctamente, pero los saltos quedan dentro de un p sin transformación estructural. insert_htmlbox trata los saltos de texto ordinarios como espacios [R1].

**Impacto.** Puede alterar instrucciones, listas, bloques de código y separación de párrafos. Es un fallo del renderizado, no necesariamente de Ollama.

**Corrección propuesta.** Distinguir saltos suaves de maquetación PDF, párrafos semánticos y saltos duros intencionados. Generar p separados, br y reglas de listas/código donde corresponda. No convertir a br todos los saltos de la extracción sin analizar su significado.

**Aceptación.** Pruebas visuales y de estructura para párrafos, viñetas, direcciones, comandos multilínea y enlaces largos. El fixture newlines.pdf documenta el comportamiento observado en la API actual.

### A08 · P1 · SQLite no conserva varios campos de la entidad

**Evidencia:** Reproducido.  
**Ubicación:** `src/domain/models/region.py; src/infrastructure/persistence/repository.py:139-190,214-235; src/infrastructure/persistence/database.py`.

Guardé y recargué una TranslationRegion real. translation_engine, translation_engine_version, target_font_size, target_font_family y fit_scale volvieron como None. El esquema/save/load no incluyen esos campos. Los SourceFragment sí conservan sus propios metadatos: el problema no implica que toda la información tipográfica se pierda.

**Impacto.** La entidad y la persistencia tienen contratos diferentes. La trazabilidad del motor y los ajustes futuros no pueden considerarse recuperables al reiniciar.

**Corrección propuesta.** Decidir campos persistentes versus derivados. Crear migración versionada para metadatos y ajustes del usuario; persistir idiomas, modelo/configuración, versiones de prompt/glosario y revisión. Los caches derivados deben regenerarse o llevar versión, no almacenarse como autoridad sin invalidación.

**Aceptación.** Roundtrip de todos los campos definidos como persistentes, migración de bases antiguas y reapertura tras cierre. Las decisiones visibles de usuario deben restaurarse sin cambio.

### A09 · P1 · Mover un PDF conserva una ruta antigua

**Evidencia:** Reproducido.  
**Ubicación:** `src/application/services/project_service.py:49-80,135-153`.

La búsqueda por fingerprint encuentra el mismo proyecto tras renombrar el PDF, pero devuelve pdf_path apuntando al nombre anterior, ya inexistente. El check de bloqueo con el archivo abierto devuelve falso; preview y export usan la ruta persistida. Existe relocate_pdf, pero no encontré su conexión al flujo de apertura de la UI.

**Impacto.** El documento puede abrirse y parecer correcto mientras operaciones posteriores fallan porque consultan otro path.

**Corrección propuesta.** Revincular de forma validada cuando hash, tamaño y cantidad de páginas coinciden, o mostrar un flujo explícito de reubicación. Mantener la identidad del proyecto y actualizar la ruta en una transacción.

**Aceptación.** Renombrar/mover el archivo, abrirlo, recuperar las regiones y exportar. Un archivo diferente con igual nombre debe mantener el bloqueo.

### A10 · P0 · Undo/Redo puede conservar acciones de otro documento

**Evidencia:** Revisión estática; pendiente de Qt.  
**Ubicación:** `src/ui/viewmodels/pdf_viewer_viewmodel.py:150-188; src/ui/views/main_window.py:276-281; src/application/commands.py`.

open_document cambia el proyecto sin limpiar el historial. La limpieza existe en close_document, pero la apertura desde MainWindow no pasa por ese cierre. Los comandos mantienen sus referencias a repositorios. Esto deja un camino para deshacer una acción del documento A mientras se muestra B.

**Impacto.** Riesgo de modificar un proyecto distinto del visible. No ejecuté este flujo con Qt; es una conclusión de las conexiones y referencias observadas.

**Corrección propuesta.** Hacer del cambio de documento una transición de sesión atómica: resolver borradores, invalidar trabajos de la sesión anterior, limpiar selección/historial/cache y enlazar el nuevo proyecto. Vincular cada comando y callback a una identidad de sesión.

**Aceptación.** Crear/editar en A, abrir B y pulsar Undo: A no debe cambiar y el historial de B debe corresponder solo a B. Repetir mientras una traducción anterior está terminando.

### A11 · P1 · La orientación raster de preview requiere validación

**Evidencia:** Revisión estática; pendiente de Qt.  
**Ubicación:** `src/infrastructure/pdf/preview_renderer.py; src/ui/components/pdf_view_widget.py:242-269; src/ui/components/translation_preview_item.py:78-113`.

La imagen de preview se produce en coordenadas nativas; la UI transforma el rectángulo y dibuja la imagen directamente en él. No encontré una transformación equivalente de los píxeles para rotaciones de página. Un bbox correcto no demuestra que el texto tenga la orientación correcta.

**Impacto.** Riesgo de texto estirado o con orientación diferente a la exportación. No presento esto como captura de GUI reproducida.

**Corrección propuesta.** Aplicar la transformación adecuada al item o a la imagen, manteniendo dimensiones, devicePixelRatio y orientación coherentes. Definir WYSIWYG como geometría/estilo equivalentes y tolerancia de rasterización, no identidad de píxeles a todo zoom.

**Aceptación.** Capturas reales Qt y raster del PDF exportado para 90/180/270 grados con texto asimétrico, a distintos zoom y escalas de Windows. Comparar contenido orientado, no solo rectángulos.

### A12 · P1 · La previsualización repite trabajo costoso antes del cache

**Evidencia:** Revisión estática; sin benchmark de hardware.  
**Ubicación:** `src/ui/viewmodels/pdf_viewer_viewmodel.py:645-688; src/application/use_cases/prepare_region_preview_use_case.py; src/infrastructure/pdf/source_inspector.py:12-51; src/infrastructure/pdf/background_analyzer.py:90-140`.

get_text_preview ejecuta preparación antes de consultar _raster_cache. El inspector calcula SHA-256 del archivo y extrae bloques de todas las páginas. El analizador recorre píxeles y exclusiones en Python y acumula tuplas. El preflight del coordinador también es síncrono. Hay exportación asíncrona, pero eso no elimina estos costes del flujo UI.

**Impacto.** El coste puede multiplicarse por regiones y refrescos. No se midieron tiempos de PDFs grandes en la PC del usuario, por lo que no atribuyo una cifra de latencia.

**Corrección propuesta.** Cachear inspección inmutable por revisión/fingerprint, luego planificación por región y finalmente raster. Invalidar solo lo afectado, limitar memoria con LRU por bytes, aplicar debounce y trasladar trabajo PDF pesado a procesos. PyMuPDF no admite multithreading como vía general segura; objetos separados y una clase stateless no cambian esa restricción [R2].

**Aceptación.** Instrumentar llamadas a inspect y layout: un zoom sin cambio semántico no debe reextraer todas las páginas por cada región. Medir p50/p95, memoria y respuesta UI con un corpus representativo y hardware documentado.

### A13 · P1 · Falta cerrar algunos estados de fallo del proceso

**Evidencia:** Revisión estática; worker normal reproducido.  
**Ubicación:** `src/infrastructure/process/export_controller.py:101-131; src/workers/pdf_export_worker.py`.

El controlador conecta stdout, stderr y finished, pero no errorOccurred. Qt diferencia FailedToStart [R3]. Falta una ruta explícita para ese fallo y un límite de espera de inicio. También conviene probar cancelación antes de READY. Por separado, ejecuté el worker real mediante subprocess: READY, STARTED, PROGRESS, COMPLETED, código 0, PDF creado y fuente intacta.

**Impacto.** El camino exitoso del worker funciona en este entorno, pero eso no certifica que todos los errores desbloqueen la interfaz o que el lanzador funcione empaquetado.

**Corrección propuesta.** Manejar errorOccurred/FailedToStart, timeout de inicio, crash, salida inesperada y cancelación temprana con una sola finalización idempotente. Diseñar un modo worker explícito del ejecutable empaquetado; no depender de sys.executable -m src... en cualquier carpeta.

**Aceptación.** Tests Qt reales para programa inexistente, permiso denegado, muerte del hijo, IPC inválido, cancelar durante STARTING y exportar otra vez. En todos, UI desbloqueada, estado terminal único y archivos temporales controlados.

### A14 · P2 · El control de depuración de fragmentos tiene interfaces incompatibles

**Evidencia:** Revisión estática.  
**Ubicación:** `src/ui/views/main_window.py:209-214; src/ui/components/pdf_view_widget.py:282; src/ui/viewmodels/pdf_viewer_viewmodel.py`.

El callback consulta viewmodel.extraction_result, pero el estado encontrado es privado (_extraction_result). Además, llama set_debug_rects con rects y mapper, cuando el método recibe solo native_rects.

**Impacto.** La opción de depuración puede lanzar AttributeError o TypeError. Es pequeño frente a los problemas de salida, pero muestra que falta comprobar conexiones UI reales.

**Corrección propuesta.** Exponer un contrato de lectura o una señal adecuada y usar una sola firma. No solucionar acoplando la vista a un atributo privado nuevo.

**Aceptación.** Activar y desactivar la casilla con y sin selección; comprobar que aparecen los bboxes correctos y que no hay excepciones.

### A15 · P1 · La suite y sus contratos están desactualizados

**Evidencia:** Reproducido con limitaciones de entorno.  
**Ubicación:** `pytest.ini; pyproject.toml; tests/unit/test_html_text_renderer.py; tests/unit/test_unicode_renderer.py; tests/unit/test_prepare_export_use_case.py; tests/unit/test_translate_region_use_case.py`.

La ejecución dirigida a tests arroja 335 passed, 31 failed, 1 skipped y 17 errores de colección. De los fallos, 29 usan contratos antiguos del renderizador; uno expone OVERFLOW convertido en UNKNOWN_BACKGROUND; uno espera marcadores BLOCK que el código ahora elimina del texto visible. Los 17 errores se deben a PySide6 no disponible. La ejecución sin tests también recoge spikes y agrega tres errores de fixtures.

**Impacto.** No existe una base reproducible que sustente hoy la afirmación de 369 tests verdes. Tampoco corresponde contar los 17 errores del entorno como 17 defectos del programa.

**Corrección propuesta.** Consolidar configuración pytest, añadir pytest-qt a dependencias de desarrollo y decidir el contrato actual de bloques. Actualizar pruebas obsoletas sin eliminar cobertura semántica. Corregir defectos reales antes de cambiar expectativas. Ejecutar ruff en el entorno objetivo; aquí no estuvo disponible.

**Aceptación.** Instalación limpia con lock de dependencias, ejecución completa en Windows y CI, tests visuales y de integración separados de Ollama real. Reportar skips esperados y ningún fallo sin explicar.

### A16 · P1 · La configuración de distribución no cubre la aplicación completa

**Evidencia:** Revisión estática; no se construyó instalador.  
**Ubicación:** `pyproject.toml:7-25; src/infrastructure/process/export_controller.py; src/main.py`.

La lista de paquetes del wheel omite src/composition, src/presentation y src/workers. La ejecución usa imports desde src. La dependencia PyMuPDF>=1.23.0 admite versiones anteriores a insert_htmlbox, incorporado en 1.23.8 [R1]. No hay una prueba realizada aquí de wheel/EXE instalado fuera del repositorio.

**Impacto.** Que python -m src.main funcione dentro de la carpeta del código no demuestra que el usuario pueda instalar y usar un ejecutable autónomo.

**Corrección propuesta.** Fijar un rango mínimo real y un lock probado. Incluir todos los componentes y recursos del paquete; definir entrypoint y modo worker. Considerar un namespace de aplicación normal cuando el baseline esté estable, no hacer una gran mudanza durante las primeras correcciones.

**Aceptación.** Construir e instalar en entorno limpio, cambiar a otra carpeta y ejecutar abrir/traducir/guardar/exportar. Repetir con paquete Windows, fuentes, rutas Unicode y sin Python de desarrollo.

### A17 · P1 · El inglés queda debajo del overlay

**Evidencia:** Reproducido; decisión de producto.  
**Ubicación:** `src/infrastructure/pdf/vector_form_exporter.py; docs/spike-report-phase-9.0.md; brain/11c48e04-a8f0-480f-9807-1aa227a9cb35/implementation_plan_v9.md`.

Los PDFs exportados conservan texto extraíble en ambos idiomas. Por ejemplo, el worker produce Hello world y Hola mundo. Esto es coherente con VECTOR_FORM_OVERLAY y con la distinción oculto/extraíble del plan recuperado.

**Impacto.** El resultado puede servir para lectura visual, pero búsqueda, copiar/pegar y accesibilidad pueden mezclar ambos textos. No es una herramienta de redacción segura ni de eliminación del contenido original.

**Corrección propuesta.** Definir y comunicar dos contratos: superposición visual y reemplazo real de texto. Para el segundo, investigar retirada de glifos nativos conservando imágenes y vectores. PyMuPDF tiene opciones de redacción que ignoran imágenes/gráficos, pero hay que verificar alcance por glifo y efectos secundarios [R1].

**Aceptación.** Testear extracción completa, búsqueda y copiar/pegar según el modo anunciado. No declarar eliminado el inglés por el solo hecho de dejar de verlo.

### A18 · P1 · La fidelidad tipográfica es parcial

**Evidencia:** Revisión estática y caso A01.  
**Ubicación:** `src/application/services/region_render_spec_planner.py:24-26,108-154; src/application/dtos/export.py:82-107; src/infrastructure/pdf/font_resolver.py; src/infrastructure/pdf/html_text_renderer.py`.

La ruta compartida usa Noto y un modelo de bloque con texto, tamaño, alineación y wrapping. No transmite todas las propiedades capturadas en la fuente, como color, negrita y cursiva por tramo. El ajuste de tamaño y la inferencia de alineación no equivalen a preservar el diseño tipográfico completo.

**Impacto.** Un documento puede mantener cajas y páginas pero perder jerarquía visual, énfasis o legibilidad. El mínimo de 6 puntos no debe convertirse silenciosamente en calidad aceptable.

**Corrección propuesta.** Diseñar un TextStyle y bloques/runs con propiedades soportadas, fallback explícito de fuente y controles manuales. Mantener el contenido traducido completo: no resumir ni omitir frases para que quepa. Ante overflow, ofrecer editar, ajustar dentro de límites o expandir con permiso.

**Aceptación.** Fixtures de títulos, negrita, cursiva, texto de color, listas, enlaces y celdas. Advertencia visible para cambios de fuente importantes, letra demasiado pequeña o estilos no soportados.

### A19 · P1 · La traducción necesita estructura persistente y controles de calidad

**Evidencia:** Revisión estática; calidad lingüística no medida.  
**Ubicación:** `src/application/use_cases/translate_region.py; src/application/services/structured_translation_codec.py; src/application/services/token_protector.py; src/infrastructure/translation/ollama_engine.py; src/domain/models/enums.py`.

Existen protección de tokens y validación de marcadores BLOCK, lo cual es valioso. Después se serializa el texto visible mediante separación por párrafos y el layout vuelve a inferir estructura. Los estados REVIEWED/READY_FOR_EXPORT no forman parte del flujo de elegibilidad actual, que acepta TRANSLATED. No evalué traducciones de un modelo real.

**Impacto.** Un resultado HTTP exitoso puede ser una traducción incompleta o inconsistente. La estructura basada en saltos de texto es frágil ante edición manual y párrafos añadidos.

**Corrección propuesta.** Guardar bloques con IDs estables separados del texto editable. Persistir motor, modelo/configuración, prompt y glosario. Añadir validación de números, unidades, tokens, cantidad de bloques y respuestas truncadas; aprovechar done/done_reason de Ollama [R5]. Incorporar revisión manual y una política explícita de aprobación.

**Aceptación.** Corpus bilingüe revisado por una persona, con terminología repetida, tablas y comandos. Validadores deterministas para elementos protegidos y pruebas de error/parcialidad del modelo. La naturalidad requiere evaluación, no solo un prompt distinto.

### A20 · P2 · Batch, OCR y autodetección siguen siendo ampliaciones

**Evidencia:** Revisión estática.  
**Ubicación:** `src/ui/viewmodels/translation_worker.py; src/ui/viewmodels/pdf_viewer_viewmodel.py; src/domain/models/enums.py`.

Hay traducción asíncrona por región, pero no encontré un gestor de lotes persistente con pausa/reanudación y selección masiva. La ausencia de texto nativo no se resuelve con OCR. La autodetección editable de regiones es otra función distinta de procesar selecciones existentes.

**Impacto.** No se debe dar por terminada la fase 7 ni asumir soporte de PDFs escaneados. Son funciones legítimas, pero no corrigen los defectos actuales de fidelidad.

**Corrección propuesta.** Implementar primero una cola acotada, de concurrencia inicial uno para el motor local, con jobs persistentes y fallos por región. Después autodetección revisable. OCR e inpainting deben ser modos separados con limitaciones propias; no enviar un libro entero como un único prompt.

**Aceptación.** Lote de varias páginas que falla parcialmente, se pausa, reinicia la app y reanuda sin repetir lo aprobado ni mezclar respuestas. Detectar escaneados y explicar el soporte disponible.

### A21 · P2 · Un PDF cifrado falla durante la inspección

**Evidencia:** Reproducido.  
**Ubicación:** `src/infrastructure/pdf/source_inspector.py:28-51`.

El inspector consulta needs_pass, pero sigue accediendo a páginas. Un PDF de prueba con contraseña devuelve ValueError: document closed or encrypted, en vez de un resultado tipado que permita manejar ENCRYPTED_SOURCE.

**Impacto.** El manejo previsto de documentos no admitidos puede degradarse a error genérico. No implica un acceso no autorizado ni un fallo criptográfico.

**Corrección propuesta.** Detener inspección de páginas antes de autenticación. Definir si v1 admite contraseña o rechaza con un mensaje claro. No registrar claves. Advertir sobre firmas antes de cualquier modificación.

**Aceptación.** PDF abierto, cifrado con clave correcta/incorrecta, firmado y corrupto. Cada uno debe tener una respuesta predecible y no dejar una sesión parcialmente inicializada.

### A22 · P2 · La vida de las conexiones SQLite no queda cerrada explícitamente

**Evidencia:** Revisión estática.  
**Ubicación:** `src/infrastructure/persistence/database.py; src/infrastructure/persistence/repository.py; src/infrastructure/persistence/factory.py`.

get_connection crea conexiones y los repositorios usan with connection. Ese contexto maneja commit/rollback, pero no cierra la conexión [R4]. El cierre de la factory no cubre todas las conexiones de archivo creadas. No medí agotamiento de recursos ni bloqueos en Windows.

**Impacto.** La liberación depende de recolección de objetos en lugar de un ciclo explícito. Puede complicar cierres, copias de seguridad y diagnóstico de locks.

**Corrección propuesta.** Usar un administrador de conexión que cierre en finally sin romper el caso especial en memoria. Para backups en caliente, usar una estrategia consistente de SQLite, no copiar solo el archivo principal ignorando WAL. Añadir migraciones con recuperación.

**Aceptación.** Abrir/cerrar repetidamente, guardar y realizar backup, restaurar y comprobar integridad. Verificar que una sesión cerrada libera sus recursos.

### A23 · P1 · La verificación final es necesaria, pero insuficiente

**Evidencia:** Revisión estática y casos A01/A02.  
**Ubicación:** `src/infrastructure/pdf/vector_form_exporter.py:30-48,290-319`.

El exportador reabre el PDF, conserva geometría y busca hasta dos tokens por región. Es una base buena, pero no detecta texto invisible, pérdidas parciales ni objetos tapados. Los casos A01 y A02 finalizan exitosamente.

**Impacto.** Validez estructural del PDF y presencia de dos palabras no equivalen a fidelidad visual o integridad completa de la traducción.

**Corrección propuesta.** Agregar verificación por bloque del texto normalizado y controles visuales sobre la máscara de edición aprobada. Comprobar invariantes fuera de esa máscara, incluyendo objetos interactivos relevantes. Mantener hash del original, temporal y reemplazo atómico; no confundir atomicidad con garantía frente a cualquier corte de energía.

**Aceptación.** Pruebas negativas de frase parcialmente ausente, color incorrecto, objeto tapado, salida corrupta y fallo a mitad de escritura. El destino previo debe conservarse cuando la operación fracasa.

### A24 · P1 · La documentación y el respaldo necesitan una nueva fuente de verdad

**Evidencia:** Inventario y revisión estática.  
**Ubicación:** `README.md; pyproject.toml; .git/; docs/; brain/11c48e04-a8f0-480f-9807-1aa227a9cb35/implementation_plan_v9.md; src/composition/translation.py`.

El ZIP contiene documentación recuperable, fases 6/8 conectadas y código con Hotfix 4/4.1 posterior al resumen. .git conserva metadatos pero no objetos/refs suficientes para recuperar commits. La mayor parte del ZIP es el entorno virtual Windows. README y resumen no coinciden con el arranque actual; el motor predeterminado es Ollama, no un fallback automático a Fake.

**Impacto.** La conversación perdida no debe seguir siendo el registro autoritativo del proyecto. El entorno virtual archivado no sustituye a dependencias reproducibles ni un historial de versiones.

**Corrección propuesta.** Crear un nuevo baseline Git del código rescatado, excluir entornos/caches, respaldar fuera de la cuenta de chat y guardar decisiones/estado por versión. Distinguir claramente motor real de fake para desarrollo. Documentar alcance, limitaciones y comando probado.

**Aceptación.** Una persona que solo recibe repositorio, lock, README y este informe puede instalar, ejecutar pruebas e identificar el siguiente ticket sin consultar conversaciones anteriores.

## 7. Arquitectura de llegada recomendada

Conservar las capas actuales, pero hacer explícito el contrato entre contenido, layout y archivo de salida:

```text
Documento fuente + fingerprint + revision de sesion
    -> Extraccion estructurada por bloques/runs
    -> Traduccion estructurada + elementos protegidos + revision manual
    -> Planificador de reemplazo y tipografia
    -> RegionRenderPlan inmutable + problemas tipados
       -> Preview raster
       -> ExportRequest serializado -> worker de exportacion
    -> Verificacion textual, visual y de archivo
```

`RegionRenderPlan` es un nombre propuesto, no una clase ya implementada. Debe incluir geometría aprobada, orientación, bloques y estilos soportados, estrategia de fondo/reemplazo, fuentes resueltas, estado de fitting, advertencias y versión del renderizador. Un resultado de planificación tiene un elemento por región, incluso cuando falla.

Preview y export deben consumir el mismo plan semántico aprobado. Pueden rasterizar a diferentes escalas para pantalla e impresión, pero no volver a tomar decisiones distintas de fuente, wrapping o geometría. La cache debe guardar trabajo ya validado; no funcionar como sustituto de la validez de un plan. El fingerprint protege la fuente, y una revisión de sesión protege contra resultados tardíos de trabajos anteriores.

Para texto enriquecido, la correspondencia entre énfasis original y traducción no siempre es mecánica. Empezar por un subconjunto de estilos bien definido y ofrecer edición manual. No vender la sustitución por Noto como preservación exacta de la fuente original.

## 8. Fondos complejos: estrategia por tipo, no una solución única

**Texto nativo sobre fondo uniforme.** Corregir primero la clasificación, el color y la geometría. Un overlay puede ser un modo válido, con la advertencia de que el inglés permanece extraíble.

**Texto nativo encima de imágenes o vectores.** Investigar eliminación selectiva de texto, preservando otros objetos. En PyMuPDF se pueden configurar redacciones para no afectar imágenes ni gráficos y sin relleno opaco; no es una garantía universal [R1]. El alcance por bbox de glifo, texto vecino, enlaces, orden de lectura y firmas obliga a una prueba específica. El rechazo del spike antiguo a una estrategia concreta no demuestra que toda variante futura sea imposible.

**Texto que forma parte de una imagen.** Es un problema distinto: OCR para reconocerlo y una estrategia de reconstrucción del fondo para reemplazarlo. Inpainting puede estimar el fondo, pero no garantiza recuperar exactamente los píxeles originales que estaban ocultos. Debe rotularse como reconstrucción aproximada y permitir revisión.

**Tablas, diagramas y fórmulas.** Empezar por regiones/celdas explícitas con obstáculos protegidos. La detección automática y la reconstrucción de tablas son funcionalidades adicionales, no consecuencias automáticas de tener OCR o un LLM.

## 9. Calidad de traducción y experiencia de uso

Una versión terminada necesita separación entre traducido, revisado, advertido y exportable. La decisión de exigir revisión antes de exportar debe ser configurable y consistente en UI, dominio y preflight.

Conviene añadir un glosario de proyecto, contexto de página/sección acotado por tokens, memoria de traducción para segmentos repetidos y validadores deterministas de cifras, unidades y tokens. Una traducción con menos líneas no es necesariamente incompleta, y una con todas las palabras clave no es necesariamente correcta: separar heurísticas de advertencia de errores demostrables.

La configuración de Ollama debe ser visible: modelo, disponibilidad, idiomas, timeout y resultado de conexión. Respetar cancelación y limitar entradas/respuestas; reintentar solo fallos transitorios de forma controlada. Los endpoints remotos, de admitirse, requieren advertir que el contenido sale del equipo. El texto fuente debe tratarse como datos, no como instrucciones capaces de alterar la tarea.

No propongo un modelo universalmente mejor sin conocer RAM, GPU, VRAM, documentos y criterios de calidad. El benchmark debe comparar modelos/configuraciones en el mismo corpus y persistir sus versiones.

## 10. Definición de terminado para una v1.0

La versión debe declarar qué PDFs y estilos admite. Para ese alcance, el flujo abrir, seleccionar, extraer, traducir, corregir, guardar, cerrar, reabrir y exportar debe funcionar desde una instalación limpia sin intervenciones sobre código o variables ocultas.

No se aceptan traducciones cortadas, invisibles, cambiadas de región o expandidas sin permiso. Lo que no se puede representar debe bloquearse o advertirse de forma explícita según severidad. La fuente debe permanecer inmutable; no se puede perder un destino anterior si falla una nueva exportación. Cada ajuste y corrección del usuario debe recuperarse al reabrir.

La preview debe concordar con la salida bajo una tolerancia documentada a escalas soportadas. Las zonas externas a las máscaras aprobadas deben conservarse visualmente dentro de la tolerancia del renderizador, y los objetos interactivos importantes deben someterse a comprobaciones propias: una comparación de píxeles no basta para enlaces o accesibilidad.

La suite debe ejecutarse de forma reproducible, con fallos resueltos y skips explícitos. Además de unit tests, se necesita QA real de Qt/Windows, instalador, reinicios, cancelación, cierres y errores de disco. El conteo de tests no sustituye esos criterios.

Las licencias se deben revisar antes de distribuir: PyMuPDF dispone de condiciones AGPL/comerciales y Qt for Python de Community LGPL/GPL y comercial [R6-R7]. Revisar también fuentes, modelos y avisos de terceros según la modalidad de distribución. Esto es una tarea de release, no un dictamen de que todo uso comercial necesite necesariamente una compra.

## 11. Documentación rescatada

El paquete de evidencias incorpora el plan antiguo `implementation_plan_v9.md`, los ADR de traducción y los reportes de spikes disponibles. El plan de fase 9 ya exigía Overflow tipado, CropBox/rotaciones, preservación del original, estrategia de proceso e información sobre inglés oculto/extraíble. Es útil como historial de intención, pero su último apartado de tareas pendientes no refleja el código actual.

El archivo `Roadmap_Traductor_PDF.md` de esta entrega es la propuesta de secuencia actual. `CONTEXTO_PARA_CONTINUAR.md` es un resumen corto para futuras sesiones. Ninguno debe marcar tareas como completadas sin nueva evidencia de pruebas.

## 12. Referencias técnicas oficiales

[R1] PyMuPDF, Page: coordenadas, CropBox, insert_htmlbox y redacciones. [R2] PyMuPDF, Multiprocessing: limitaciones de multithreading. [R3] Qt for Python, QProcess: errorOccurred y FailedToStart. [R4] Python, sqlite3: el contexto de conexión no la cierra. [R5] Ollama, Generate a response: campos de terminación y configuración. [R6] PyMuPDF, licencia del repositorio y opciones de distribución. [R7] Qt for Python, Commercial Use/Qt Licensing. Consultadas el 5 de septiembre de 2026.

```text
R1 https://pymupdf.readthedocs.io/en/latest/page.html
R2 https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html
R3 https://doc.qt.io/qtforpython-6/PySide6/QtCore/QProcess.html
R4 https://docs.python.org/3/library/sqlite3.html
R5 https://docs.ollama.com/api/generate
R6 https://github.com/pymupdf/PyMuPDF/blob/main/COPYING
   https://pymupdf.io/
R7 https://doc.qt.io/qtforpython-6.10/commercial/index.html
   https://doc.qt.io/qt-6.11/licensing.html
```

## 13. Identidad de la copia auditada

```text
Archivo: Traductor.zip
SHA-256: 8623e526a396105f9ae8404eba460ab5e19c4406bd4db9b25d17c5cddb9bb073
Entradas del ZIP: 7215
Bytes comprimidos: 298359814
```
