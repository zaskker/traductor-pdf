# Spike Report Phase 9.0: Export Strategy (Final)

## A. Background Classification & Safe Fallback
El clasificador fue reescrito para excluir los píxeles del texto original (SourceFragments bounding box) y evaluar la varianza tanto del perímetro como interior. Se implementó una política segura (fail-safe) que dictamina `COMPLEX_BACKGROUND` ante incertidumbre.

| Fixture | Expected | Actual | Pass | Dominant | Perim. Var | Int. Var |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| fixture_a_white.pdf | UNIFORM_WHITE | UNIFORM_WHITE | True | RGB(255, 255, 255) | 0.0 | 0.0 |
| fixture_b_gray.pdf | UNIFORM_COLOR | UNIFORM_COLOR | True | RGB(204, 204, 204) | 0.0 | 0.0 |
| fixture_c_line.pdf | COMPLEX_BACKGROUND | COMPLEX_BACKGROUND | True | RGB(255, 255, 255) | 666.1 | 2954.9 |
| fixture_d_raster.pdf | COMPLEX_BACKGROUND | COMPLEX_BACKGROUND | True | RGB(0, 255, 0) | 0.0 | 28014.3 |
| fixture_e_vector.pdf | COMPLEX_BACKGROUND | COMPLEX_BACKGROUND | True | RGB(255, 255, 255) | 6594.2 | 7989.9 |

**Reproducción Color Uniforme:** Para fondos grises detectados, el overlay vectorial se aplicó automáticamente usando el RGB extraído, logrando enmascarar el contenido inferior conservando la estética.

## B. Rotation & CropBox Placement
Se evaluó la hipótesis de 'Temporary Derotation' (rotar a 0 -> show_pdf_page -> restaurar rotación original) vs inserción nativa sin alterar la rotación.

| Strategy | Case | Pass (<= 0.5pt) | X Error (pt) | Y Error (pt) |
| :--- | :--- | :--- | :--- | :--- |
| VECTOR_FORM_fixture_g_rot_0.pdf | True | 0.00 | 0.00 |
| VECTOR_DEROTATED_fixture_g_rot_0.pdf | True | 0.00 | 0.00 |
| VECTOR_FORM_fixture_g_rot_90.pdf | True | 0.00 | 0.00 |
| VECTOR_DEROTATED_fixture_g_rot_90.pdf | True | 0.00 | 0.00 |
| VECTOR_FORM_fixture_g_rot_180.pdf | True | 0.00 | 0.00 |
| VECTOR_DEROTATED_fixture_g_rot_180.pdf | True | 0.00 | 0.00 |
| VECTOR_FORM_fixture_g_rot_270.pdf | True | 0.00 | 0.00 |
| VECTOR_DEROTATED_fixture_g_rot_270.pdf | True | 0.00 | 0.00 |
| VECTOR_FORM_fixture_g_crop.pdf | True | 0.00 | 0.00 |
| VECTOR_DEROTATED_fixture_g_crop.pdf | True | 0.00 | 0.00 |
| VECTOR_FORM_fixture_g_rot_0_crop.pdf | True | 0.00 | 0.00 |
| VECTOR_DEROTATED_fixture_g_rot_0_crop.pdf | True | 0.00 | 0.00 |
| VECTOR_FORM_fixture_g_rot_90_crop.pdf | False | 50.00 | 50.00 |
| VECTOR_DEROTATED_fixture_g_rot_90_crop.pdf | True | 0.00 | 0.00 |
| VECTOR_FORM_fixture_g_rot_180_crop.pdf | False | 50.00 | 50.00 |
| VECTOR_DEROTATED_fixture_g_rot_180_crop.pdf | True | 0.00 | 0.00 |
| VECTOR_FORM_fixture_g_rot_270_crop.pdf | False | 50.00 | 50.00 |
| VECTOR_DEROTATED_fixture_g_rot_270_crop.pdf | True | 0.00 | 0.00 |

**Conclusión de Placement:** La derotación temporal es la política productiva requerida. Evita el offset asimétrico causado por la superposición de CropBoxes desplazados sobre el centro de rotación.

## C. Benchmark (100 Regiones Únicas)
Se probó sobre un documento sintético de 10 páginas y 100 regiones únicas y no superpuestas, aplicando `VECTOR_FORM` real. El overhead listado es contra un baseline guardado con `deflate=True` para aislar el peso del overlay del de recompresión general.

| Case ID | Applied | Baseline Size | Output Size | True Overhead | Elapsed ms |
| :--- | :--- | :--- | :--- | :--- | :--- |
| bench_VECTOR_FORM_1 | 1 | 21392 b | 22222 b | +830 b | 13.1 ms |
| bench_VECTOR_FORM_10 | 10 | 21392 b | 29582 b | +8190 b | 90.4 ms |
| bench_VECTOR_FORM_25 | 25 | 21392 b | 41887 b | +20495 b | 213.5 ms |
| bench_VECTOR_FORM_100 | 100 | 21392 b | 103369 b | +81977 b | 869.8 ms |

## D. Raster Zoom
La renderización de Raster PNG como alternativa queda descartada para el MVP productivo debido a: su naturaleza no-searchable, mayor overhead de archivo y resolución fija (se vuelve borroso a grandes aumentos).

## E. Strategy Parity Control
| Strategy | Spanish Searchable | Changed Pixel Ratio |
| :--- | :--- | :--- |
| **DIRECT_NATIVE** | True | 0.1880 |
| **VECTOR_FORM** | True | 0.0000 |

## F. MVP Policy y Arquitectura Definitiva
1. **Content**: `VECTOR_FORM_OVERLAY` usando *temporary derotation* para garantizar placement píxel-perfecto.
2. **Background MVP**: Soportar explícitamente `UNIFORM_WHITE` y `UNIFORM_COLOR`. Las regiones `COMPLEX_BACKGROUND` quedarán temporalmente bloqueadas para evitar parches visibles que tapen gráficos relevantes.

## G. Confirmación
FASE 9 PRODUCTIVA NO INICIADA.