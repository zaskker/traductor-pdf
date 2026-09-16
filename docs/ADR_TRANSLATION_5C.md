# ADR: Translation Architecture (Phase 5C - Ollama Engine)

## Contexto
En la Fase 5C se implementó el motor de traducción real utilizando Ollama, reemplazando el `FakeTranslationEngine` usado en pruebas, pero manteniendo el pipeline asíncrono y de protección de tokens desarrollado en Fases 5A/5B.

## Decisiones Arquitectónicas

1.  **Nuevo Contrato del Motor (`ITranslationEngine`)**:
    *   Firma actualizada: `translate(system_prompt: str, user_prompt: str) -> TranslationResult`.
    *   La responsabilidad de construir las instrucciones y proteger los delimitadores recae en `TranslationPromptBuilder` (Application), no en la capa de Infraestructura.
    *   `TranslationResult` ya no contiene el `source_text`. La validación de que un source no vacío no devuelva una traducción vacía ahora se realiza en `TranslateRegionUseCase`.

2.  **API y Cliente HTTP**:
    *   Uso de **`urllib.request`** de la biblioteca estándar de Python. No se incluyeron dependencias de terceros como `requests`, `httpx` ni clientes oficiales de Ollama.
    *   El endpoint utilizado es `POST /api/generate`. No se usa `/api/chat`.
    *   Generación en bloque continuo (`stream: false`). El texto se recibe completo antes de ser procesado para garantizar su integridad.

3.  **Configuración y Límite de Tiempo**:
    *   La política de timeout no es un deadline absoluto. El `timeout_seconds` (por defecto 300) se pasa directamente al socket subyacente de `urllib`, aplicando a las operaciones bloqueantes.
    *   La configuración (`OllamaConfig`) permite especificar el `host`, `model` y `timeout_seconds` mediante variables de entorno (`OLLAMA_HOST`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`).

4.  **Límites de Prompt y Privacidad (Privacy-First)**:
    *   Se envían los datos encerrados estrictamente en delimitadores (`<TRANSLATION_SOURCE>`). Los delimitadores literales presentes en el source original se escapan (`<\TRANSLATION_SOURCE>`) para evitar prompt injection.
    *   **Prohibición de Logs de Contenido**: Bajo ninguna circunstancia el motor registra, imprime o expone el texto fuente, las instrucciones generadas, el texto protegido o la traducción resultante, garantizando privacidad absoluta de los documentos procesados.

5.  **Manejo de Errores Riguroso**:
    *   Se mapean exhaustivamente todos los errores HTTP (Connection Refused, Timeouts, 404 Model Not Found, 500) a excepciones nativas del dominio (`TranslationEngineError`, `TranslationTimeoutError`).
    *   Errores dudosos de serialización JSON (o campos faltantes/vacíos) se rechazan de inmediato lanzando `InvalidTranslationResultError`.
    *   Ninguna excepción de red expuesta cruda (ej. `URLError`) llega a las capas superiores.

6.  **Inicialización (Lazy Startup y Factory)**:
    *   Se utiliza un Factory (`create_translation_engine()`) configurado mediante la variable `TRANSLATOR_ENGINE`.
    *   El sistema inicia sin hacer "health checks" a Ollama. Esto permite usar la aplicación libremente para extraer y guardar regiones sin requerir que Ollama esté funcionando hasta que se presione "Translate".
    *   Queda estrictamente **prohibido** ejecutar subprocesos para instalación automática, `ollama pull` u `ollama run`. El usuario es responsable de disponer del modelo y el servicio.
