# Estado Actual (Revisado Localmente)

**Fecha de ejecución:** 5 de septiembre de 2026.
**Entorno observado:** Windows 10/11. Ejecución mediante `.\.venv\Scripts\python.exe`.
**Directorio de trabajo:** `C:\Users\Franco\Desktop\Traductor`

## 1. Comprobaciones de Ejecución (Pytest)
Se generó el log de la suite actual mediante:
`.\.venv\Scripts\python.exe -m pytest tests -q --continue-on-collection-errors > recovery\evidencias\pytest_log_local.txt 2>&1`

**Resultado Real obtenido:** `30 failed, 267 passed, 1 skipped, 19 warnings, 146 errors in 6.36s`

### 1.1 Diagnóstico del log (PermissionError)
- Se inspeccionó el log localmente. Los 146 errores no corresponden a fallos funcionales o de aserción independientes, sino que se originan (mayoritariamente) en un `PermissionError: [WinError 5] Acceso denegado: 'C:\\Users\\User\\AppData\\Local\\Temp\\pytest-of-User'`.
- **Naturaleza del Error:** Fallos en la fase de **teardown**. El *fixture* subyacente de `pytest` (o el interceptor de `pytest-qt`) intenta borrar el directorio temporal usado en los tests.
- **Hipótesis fundamentada:** Bajo Windows, la eliminación de un directorio falla si existen descriptores de archivo (file handles) aún abiertos. Esto sucede cuando instancias productivas de persistencia (SQLite, conexiones con `.db` o ficheros `.db-wal`) o handles sobre archivos físicos `.pdf` desde PyMuPDF (`fitz.Document()`) se omiten de cerrar explícitamente (`.close()`) durante la ejecución o al ser destruidos.
- **Conclusión sobre A22:** La cantidad de errores confirma que el lifecycle de *ownership* está incompleto, pero no confirma intrínsecamente un *memory leak*. La causa raíz (sea en SQLite, en PyMuPDF, o en fixtures) debe ser diagnosticada en la Iteración 1, diferenciando problemas del test de defectos en producción.

## 2. Diferencias clave frente a la Auditoría Histórica
- La ejecución original de auditoría (Linux) reportó 17 errores por la falta de `PySide6`. En este entorno de Windows *con PySide6 aparentemente presente en el venv*, surgen en cambio los masivos problemas de `PermissionError` por teardown.
- Las **Fases 6 y 8 históricas** se mantienen integradas (visto en `src/main.py:31-61`). El código productivo inyecta las implementaciones basadas en `PyMuPDF`.

## 3. Limitaciones de esta revisión
- No se corrieron pruebas como Administrador, ni se apagaron protecciones de archivos, ni se alteró el entorno para silenciar los `PermissionError`. El log se ha preservado "tal cual" (as is) en `recovery/evidencias/pytest_log_local.txt`.
- No se han identificado unívocamente las líneas exactas de código productivo culpables de los handles abiertos (esto requerirá depuración durante la Iteración 1).
