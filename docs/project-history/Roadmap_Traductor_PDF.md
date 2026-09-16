# Roadmap reconstruido: Traductor PDF

**Baseline:** ZIP auditado el 5 de septiembre de 2026.  
**Estado:** MVP avanzado, refactorización de layout/preview pendiente de estabilizar.  
**Regla:** una tarea está terminada cuando su criterio de aceptación tiene evidencia; no cuando existe un archivo con su nombre.

Este plan conserva el trabajo existente. Las fases antiguas 6 y 8 no se deben empezar de cero; se deben consolidar. Las estimaciones de calendario requieren conocer disponibilidad, hardware y PDFs objetivo. El orden siguiente se basa en dependencias y riesgo, no en un porcentaje ficticio de avance.

## Alcance propuesto para v1.0

Aplicación Windows local para PDFs con texto nativo: seleccionar regiones, revisar texto fuente, traducir al español, corregir manualmente, ajustar tipografía dentro de reglas conocidas, guardar y reabrir proyectos, y exportar una copia conservando las zonas no editadas. Soporte inicial de fondos y estilos expresamente validado; los casos no soportados se explican y no se exportan silenciosamente.

Decidir y mostrar si el modo de salida es overlay visual con inglés subyacente o reemplazo real de texto. OCR, reconstrucción de fondos raster, traducción de fórmulas y tablas complejas no se consideran automáticamente incluidos. Pueden añadirse sin impedir cerrar una v1.0 nativa confiable. El batch sí forma parte del producto deseado, pero se construye sobre el flujo individual ya estabilizado.

## Hito 0. Rescate y baseline reproducible

**Dependencia:** ninguna. **Hallazgos:** A15, A16, A24.

| Ticket | Entrega | Aceptación |
|---|---|---|
| BASE-01 | Repositorio limpio, backup externo y commit de rescate | El código y sus decisiones no dependen de una cuenta de chat; .venv y caches no se versionan |
| BASE-02 | Dependencias de ejecución/desarrollo bloqueadas | Instalación limpia documentada con versiones objetivo y pytest-qt incluido |
| BASE-03 | Una sola configuración pytest | El comando por defecto recoge tests, no spikes accidentales |
| BASE-04 | Contratos HTML/Unicode actualizados | Mantener pruebas de acentos, viñetas, enlaces y bloques; resolver fallos de interfaz sin perder cobertura |
| BASE-05 | Registro de limitaciones y CI | Separar unitarios, Qt, PDFs y Ollama real; ruff y resultados de cada grupo reproducibles |

Primero conservar el resultado rojo actual como evidencia. No arreglar todos los fallos cambiando expectativas. El test de overflow está detectando un defecto real; el de marcadores exige decidir cómo se conserva la estructura sin mostrar etiquetas internas al usuario.

## Hito 1. Correcciones que impiden pérdida visual o de proyecto

**Dependencia:** baseline identificable, no es necesario esperar a toda la limpieza de estilo. **Hallazgos:** A01-A06, A09-A10.

| Ticket | Entrega | Aceptación |
|---|---|---|
| SAFE-01 | Resultados tipados del planificador por región | OVERFLOW, COMPLEX_BACKGROUND y UNKNOWN no se confunden y llevan región/página |
| SAFE-02 | Contrato canónico de coordenadas | Fixture de CropBox desplazado y matriz de rotaciones pasan extracción y exportación |
| SAFE-03 | Relleno/color seguro | Texto blanco sobre negro visible o exportación bloqueada de forma explícita |
| SAFE-04 | Detección conservadora de objetos bajo texto | La línea azul no desaparece en un resultado declarado seguro |
| SAFE-05 | Región fija por defecto | No hay ampliación geométrica silenciosa; una ampliación exige aprobación |
| SAFE-06 | Transición de documento segura | Undo en B no modifica A; callbacks antiguos no afectan la nueva sesión |
| SAFE-07 | Reubicación por fingerprint validado | Mover el PDF mantiene proyecto utilizable y actualiza la ruta |
| SAFE-08 | Exportación parcial coherente | Se puede confirmar solo traducidas sin omitir bloqueos adicionales |

Este hito puede cerrar temporalmente ciertos casos mediante un bloqueo seguro. Eso evita resultados dañados mientras se amplía el soporte, pero el bloqueo debe figurar como limitación y no como soporte completo.

## Hito 2. Consolidar fases 6 y 8: un solo plan de renderizado

**Dependencia:** SAFE-01/02/05. **Hallazgos:** A05, A07, A11, A18, A23.

| Ticket | Entrega | Aceptación |
|---|---|---|
| RENDER-01 | Plan inmutable/versionado con geometría y bloques | Preview y export consumen la misma decisión de layout, fuente y wrapping |
| RENDER-02 | Estilos explícitos soportados | Color, tamaño, alineación, negrita/cursiva y fallback siguen una política probada |
| RENDER-03 | Párrafos, listas y saltos duros | No se pierde estructura ni se convierten todos los saltos suaves en br |
| RENDER-04 | Fitting legible y diagnosticable | Límites configurables; texto completo; sin recorte ni resumen silencioso |
| RENDER-05 | Orientación y escala de preview | Capturas Qt concuerdan con la salida en rotaciones y escalas de Windows soportadas |
| RENDER-06 | Validación por bloque y visual | Texto completo, colores visibles y zonas externas preservadas; no solo dos tokens |

El tamaño original es una preferencia, no una garantía cuando el español ocupa más. Ante un conflicto: mantener la región, ajustar dentro de límites de legibilidad, informar el conflicto y permitir corrección humana. No añadir una segunda fuente de verdad mediante un layout independiente en Qt.

## Hito 3. Proyectos durables y recuperables

**Dependencia:** contratos de datos del hito 2 definidos. **Hallazgos:** A08-A10, A22.

| Ticket | Entrega | Aceptación |
|---|---|---|
| DATA-01 | Migración SQLite y contrato de persistencia | Todos los campos persistentes sobreviven a save/load y bases antiguas se migran |
| DATA-02 | Bloques traducidos con IDs estables | La edición visible no destruye la correspondencia con la fuente |
| DATA-03 | Metadatos del proyecto | Idiomas, motor/modelo, prompt, glosario, opciones y revisiones recuperables |
| DATA-04 | Abrir/guardar/copiar/restaurar proyecto | Flujo visible, detección de fuente modificada y reubicación segura |
| DATA-05 | Backup y conexiones con ciclo explícito | Cierre libera recursos; backup/restauración conserva integridad con WAL |

No es obligatorio persistir toda la pila Undo en v1.0, pero sí es obligatorio no perder las ediciones ya guardadas. La decisión sobre el historial debe documentarse y mantenerse aislada por proyecto.

## Hito 4. Calidad y control del motor de traducción

**Dependencia:** datos y estructura estables. **Hallazgos:** A19, A24.

| Ticket | Entrega | Aceptación |
|---|---|---|
| TRANS-01 | Configuración visible y comprobación de disponibilidad | Ollama ausente/modelo inexistente se explican; Fake queda marcado como desarrollo |
| TRANS-02 | Errores, timeout y cancelación | No se aplica una respuesta cancelada/tardía; reintentos acotados solo donde corresponde |
| TRANS-03 | Salida estructurada validada | IDs/cantidad de bloques y tokens protegidos coherentes; detectar truncamiento |
| TRANS-04 | Glosario y consistencia | Términos y segmentos repetidos mantienen traducción o advertencia |
| TRANS-05 | Revisión y aprobación | Estados de dominio, UI y preflight comparten reglas de exportabilidad |
| TRANS-06 | Evaluación bilingüe | Corpus revisado con criterios de exactitud, omisiones, terminología y naturalidad |

Proteger también cifras, unidades, nombres propios cuando aplique, rutas y comandos. No confundir el mismo número de caracteres con fidelidad. Documentar qué se envía al motor y evitar contenido completo en logs por defecto.

## Hito 5. Rendimiento y batch de regiones existentes

**Dependencia:** flujo individual correcto y cancelación fiable. **Hallazgos:** A12, A20.

| Ticket | Entrega | Aceptación |
|---|---|---|
| PERF-01 | Inspección y plan cacheados antes del raster | Refrescar/zoom no recalcula el documento entero por región |
| PERF-02 | Trabajo PDF pesado fuera de UI | Navegar y cancelar siguen respondiendo; no introducir multithreading PyMuPDF inseguro |
| PERF-03 | LRU por memoria y debounce | La memoria no crece sin límite con documentos/regiones/zoom |
| BATCH-01 | Selección múltiple y cola acotada | Traducir selección, página o pendientes; sin lanzar cargas ilimitadas |
| BATCH-02 | Jobs persistentes y resultados parciales | Pausa, cancelación, reinicio y reanudación sin mezclar regiones |
| BATCH-03 | Progreso y retry selectivo | Un error no pierde las traducciones exitosas; se reintenta solo lo elegido |

Concurrencia inicial propuesta: un trabajo de generación por modelo local, ajustable después de medir. Batch es orquestación de trabajos, no obligatoriamente un prompt gigante. La autodetección editable de bloques puede añadirse después de la cola.

## Hito 6. Ampliar fondos y reemplazo nativo sin promesas universales

**Dependencia:** corpus visual y contrato compartido. **Hallazgos:** A02, A17.

| Ticket | Entrega | Aceptación |
|---|---|---|
| BG-01 | Spike de retirada de texto nativo | Matriz de imágenes, líneas, vectores, texto vecino y enlaces preservada |
| BG-02 | Selector de estrategia explicable | Overlay, reemplazo nativo o no soportado con motivos claros |
| BG-03 | Copiar/pegar y búsqueda coherentes | Se cumple el contrato anunciado sobre inglés oculto o eliminado |
| BG-04 | OCR/reconstrucción como extensión independiente | Modo opcional con advertencia de aproximación y revisión del resultado |

BG-01 a BG-03 son necesarios antes de anunciar reemplazo real o fondos complejos nativos en general. BG-04 puede ser v1.1/v2 si v1 declara soporte de texto nativo. No retrasar todas las correcciones anteriores esperando resolver inpainting perfecto.

## Hito 7. Robustez del proceso, instalación y QA de release

**Dependencia:** funciones incluidas en la versión estabilizadas. **Hallazgos:** A13-A16, A21-A24.

| Ticket | Entrega | Aceptación |
|---|---|---|
| RELEASE-01 | Estados terminales del worker/coordinador | FailedToStart, crash, timeout e IPC inválido desbloquean una sola vez |
| RELEASE-02 | Modo worker del ejecutable | Funciona fuera del repo y sin Python de desarrollo |
| RELEASE-03 | Manejo de documentos y archivos problemáticos | Cifrado, firma, corrupción, permisos, destino abierto y disco insuficiente controlados |
| RELEASE-04 | Paquete completo y recursos | UI, composition, workers y fuentes requeridas incluidos; instalación limpia |
| RELEASE-05 | Licencias/avisos/documentación | Condiciones de bibliotecas, modelos y fuentes revisadas para la distribución elegida |
| RELEASE-06 | Prueba de aceptación Windows | Flujo completo manual, DPI, rutas Unicode, reinicios y cancelaciones |

Un instalador no es el primer paso: empaquetar los defectos no los resuelve. Pero se debe probar un artefacto empaquetado antes de declarar finalizada la versión.

## Matriz de QA propuesta

Construir un corpus versionado y redistribuible; como punto de partida propuesto, unos 30-50 PDFs pequeños representativos más documentos grandes para rendimiento. La cifra es un objetivo de trabajo, no una cantidad ya auditada. Cada fixture debe tener licencia/procedencia clara y el resultado esperado.

Cubrir texto nativo simple, fuentes y símbolos españoles, negrita/cursiva, listas/URLs/código, multicolumna, celdas, texto blanco, fondos de color, gráficos bajo texto, CropBox desplazado, rotaciones y combinaciones. Añadir documentos escaneados, cifrados y firmados para verificar rechazo/advertencia, no para fingir soporte.

Probar también operaciones: abrir B durante trabajo en A, editar mientras llega una respuesta, cerrar con borrador, reabrir, mover la fuente, alterar su contenido, cancelar en cada fase y reexportar. Fuera de la máscara aprobada, exigir equivalencia visual con tolerancia registrada; dentro, exigir contenido completo y legible. La máscara aprobada no puede ser una ampliación silenciosa usada para esconder diferencias.

Medir rendimiento en hardware identificado: tiempo de primera página, refresco con regiones, preflight, traducción, exportación y memoria. Establecer los umbrales finales después del baseline; no inventar una promesa de latencia sin medir.

## Primera iteración recomendada

Limitar el primer cambio a BASE-01/03/04 y SAFE-01: salvar el estado, fijar colección de tests, alinear la API del renderizador sin perder verificaciones y devolver causas de error por región. Agregar al repositorio los fixtures diagnósticos como tests de regresión con aserciones de comportamiento deseado; los scripts de auditoría actuales documentan comportamiento observado y no reemplazan esos tests.

La segunda iteración debe abordar SAFE-02/03/04/05: geometría, contraste, objetos tapados y límites de selección. Resolver SAFE-06 antes de permitir uso habitual con múltiples documentos. No incorporar todavía OCR, interfaz nueva o un cambio de arquitectura general.

## Puerta de salida de v1.0

Solo cerrar la versión cuando el alcance admitido esté documentado y el flujo completo pase desde una instalación limpia. Deben quedar cero errores conocidos que produzcan pérdida silenciosa, ningún P0 abierto, pruebas acordes al contrato y evidencia de recuperación de proyectos. Los P1 restantes deben estar resueltos o fuera del alcance de la versión de manera explícita y verificable, no escondidos como advertencias genéricas.
