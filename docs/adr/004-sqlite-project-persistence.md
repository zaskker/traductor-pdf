# 004 - SQLite Project Persistence

**Status:** Aprobado (Fase 0)

**Context:**
La aplicación procesará libros PDF que pueden tener cientos de páginas. Las traducciones, ajustes tipográficos, y previsualizaciones pueden tardar días en completarse. La aplicación requiere un sistema persistente para no perder el progreso si la aplicación se cierra, o si el usuario quiere pausar su trabajo. El usuario debe poder recuperar su trabajo 100% de manera local y desconectada, sin dependencias complejas.

**Decision:**
Usaremos **SQLite** como base de datos local para almacenar proyectos, regiones y traducciones. Se activará el modo WAL (Write-Ahead Logging) para permitir autoguardado (autosave) concurrente sin bloquear operaciones de lectura, asegurando una persistencia transaccional rápida durante ediciones continuas.
El repositorio estará aislado en la capa `Infrastructure`. El dominio recibirá y retornará entidades puras (Data Classes). No usaremos un ORM pesado (como SQLAlchemy) a menos que la complejidad del esquema lo haga estrictamente necesario; inicialmente bastará la librería `sqlite3` estándar con sentencias SQL preparadas para maximizar rendimiento y reducir dependencias.

**Consequences:**
* **Positivo:** Todo el estado del proyecto reside en un único archivo portátil (.sqlite).
* **Positivo:** Guardado progresivo sin bloqueos usando transacciones.
* **Negativo:** Migrar el esquema de SQLite en versiones futuras puede requerir scripts manuales (ej. Alembic) si no usamos un ORM pesado.
