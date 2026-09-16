# ADR: Translation Architecture (Fase 5B)

## Contexto
Durante la Fase 5B se procedió a la integración de la traducción en el flujo asíncrono de la aplicación, utilizando un Fake Engine como demostrador/tester tecnológico antes de integrar Ollama en Fase 5C.

## Decisiones Implementadas

### 1. TranslateRegionUseCase
- **Decisión**: Implementado para orquestar la copia del snapshot anterior (`old_region`), la aplicación del `TokenProtector` y el `TranslationPromptBuilder`, y la generación de un nuevo snapshot (`new_region`).
- **Justificación**: Aísla la regla de negocio y evita que el engine maneje estados o interacciones de persistencia. Devuelve las versiones antes y después que `TranslateRegionCommand` utilizará.

### 2. TranslateRegionCommand
- **Decisión**: Integrado en el `CommandHistory`.
- **Justificación**: `execute` y `redo` persisten la `new_region`, `undo` persiste la `old_region`. De esta manera, el Engine se invoca UNA sola vez durante todo el ciclo de vida del comando, asegurando inmutabilidad y eficiencia.

### 3. Invalidation en Move/Resize
- **Decisión**: La validación exige que `new_source_text == old_source_text` para preservar la traducción (match exacto). Cualquier diferencia, incluso de espacios en blanco, reinicia la traducción y el estado a `PENDING`.
- **Justificación**: Política ultra estricta que previene desajustes espaciales o desincronización texto/traducción.

### 4. Async Architecture & QThreadPool
- **Decisión**: El asincronismo se restringe EXCLUSIVAMENTE a la capa de UI. Se emplea `QRunnable` (`TranslationWorker`) gestionado por `QThreadPool`. La capa `Application` corre sincrónicamente.
- **Justificación**: Evita contaminar la capa de aplicación con APIs de asincronía y simplifica fuertemente las pruebas.

### 5. in-flight Guards
- **Decisión**: El ViewModel mantiene una estructura `set[str]` para rechazar traducciones simultáneas de una misma región. Se permite la traducción concurrente de regiones diferentes.
- **Justificación**: Evita el envío doble del mismo request que podría corromper la BD al resolverse.

### 6. Stale-Result Identity
- **Decisión**: Al completarse un worker, el ViewModel valida que el contexto siga vigente antes de confirmar la mutación (misma región, mismo source_text, mismo updated_at y mismo proyecto activo).
- **Justificación**: Garantiza la seguridad de los datos frente a modificaciones concurrentes (Delete, Move, Close Project) sin requerir costosas o frágiles rutinas de cancelación del worker.

### 7. Non-cancellation Policy
- **Decisión**: Las llamadas a translation engines (que pueden ser procesos bloqueantes a nivel OS) no se cancelan forzosamente. En su lugar, el resultado se ignora vía la política de Stale-Result.

## Notas Adicionales
- La Fase 5C (Ollama, Engine Real) NO ha sido iniciada.
