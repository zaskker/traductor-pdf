# 001 - MVVM Layered Architecture

**Status:** Aprobado (Fase 0)

**Context:**
La aplicación es una interfaz de escritorio compleja en PySide6 que requiere manipulación del sistema de archivos, bases de datos, APIs de traducción, e interacción directa con archivos PDF. Históricamente, las aplicaciones Qt tienden a mezclar la lógica de negocio directamente dentro de los widgets, lo cual dificulta el testing, acopla los motores al UI y dificulta el mantenimiento a largo plazo.

**Decision:**
Adoptaremos una arquitectura basada en **MVVM simplificado** combinada con **Separación por Capas**.
Se establecen cuatro capas estrictas:
1. **UI (Views & ViewModels)**
2. **Application (Orquestación, Commands, Use Cases)**
3. **Domain (Reglas de negocio puras, Value Objects, Interfaces)**
4. **Infrastructure (PyMuPDF, SQLite, Requests)**

Las capas inferiores no pueden depender de las capas superiores. Específicamente, el `Domain` no puede importar nada relacionado con Qt, PyMuPDF, SQLite o librerías externas. Todo el acceso a la infraestructura concreta se realizará mediante el patrón de Inversión de Dependencias, definiendo puertos (interfaces) en el `Domain` y adaptadores en `Infrastructure`.

**Consequences:**
* **Positivo:** La lógica de dominio es fácil de testear sin instanciar ventanas Qt.
* **Positivo:** Podemos cambiar el motor de traducción o el sistema de base de datos sin afectar a la UI ni a la lógica core.
* **Negativo:** Mayor verbosidad inicial al requerir crear DTOs, interfaces y ViewModels para acciones que de otro modo serían un simple "on_click" en un botón.
