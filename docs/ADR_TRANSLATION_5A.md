# ADR: Translation Architecture (Phase 5A Partial)

## Context
Se requiere introducir un motor de traducción local, manteniéndolo desconectado de la capa de UI inicialmente y aislando sus componentes de dominio e infraestructura.

## Decisions

### 1. Translation Port and Adapters
- **Decisión**: Se declara `ITranslationEngine` en Dominio (`src/domain/interfaces/translation.py`). `TranslationResult` expone `translated_text`, `engine_name` y `model_name`. `model_name` puede estar vacío si el engine no expone un modelo específico (ej. FakeEngine).
- **Justificación**: Aísla el dominio de implementaciones tecnológicas específicas (ej. Ollama o HTTP requests).

### 2. FakeTranslationEngine
- **Decisión**: Se provee `FakeTranslationEngine` en `src/infrastructure/translation/fake_engine.py`.
- **Justificación**: Permite probar exhaustivamente la orquestación, el manejo asíncrono y los comandos sin red, esperas, o dependencias externas.

### 3. TokenProtector en Application
- **Decisión**: El componente `TokenProtector` pertenece a `src/application/services/token_protector.py`.
- **Justificación**: Proteger tokens técnicos antes de enviarlos a traducir es un requerimiento del pipeline (Use Case), no una regla invariante de la entidad `TranslationRegion`.
- **Contrato de Placeholder**: Se fija a `[[TP_XXXX]]` y se protege contra mutaciones con validación estricta al restaurar (rechazando duplicados, desaparecidos o modificados).

### 4. TranslationPromptBuilder
- **Decisión**: La construcción de las instrucciones que se envían al motor pertenece a `src/application/services/prompt_builder.py`.
- **Justificación**: El Engine no debe conocer las reglas de negocio (ej. preservar `[[TP_XXXX]]`). Su responsabilidad es puramente de transporte/ejecución del LLM.

## Consequences
- El Dominio permanece inmaculado respecto a librerías de red, LLM o parsing pesado de UI.
- La suite de tests es rápida y determinista.
- Las fases 5B y 5C tendrán componentes acotados con interfaces claras para su orquestación y transporte.
