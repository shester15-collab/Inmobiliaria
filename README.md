# Estimación Inmobiliaria — Fase 1

Prototipo experimental de comparación de propiedades, Python 3.10+ y biblioteca estándar.

## Archivos
- `data/jardines_del_bosque.json`: 11 publicaciones recopiladas manualmente.
- `engine/estimator.py`: deduplicación conservadora, similitud y estimación preliminar.
- `tests/test_estimator.py`: pruebas básicas.

## Ejecutar
Desde la carpeta del proyecto:

```bash
python -m unittest discover -s tests -v
python engine/estimator.py
```

## Limitaciones importantes
- CASA-03/CASA-09 se cuentan como una sola por pertenecer al mismo grupo de probable duplicado; requiere verificación humana.
- Los precios son precios de publicación, no precios de cierre.
- El score es un prototipo heurístico, no un modelo inmobiliario validado.
- El rango es descriptivo, no un intervalo estadístico de confianza.
- La estimación solo es experimental: 10 propiedades únicas es una muestra pequeña y heterogénea.
- No se ajusta automáticamente el precio por estado legal, condición, antigüedad, ubicación exacta o remodelación, porque esos datos faltan.

## Criterios del motor
- La similitud combina coincidencia física y cobertura ponderada: un campo ausente no es una coincidencia y reduce la puntuación. Los campos no numéricos, booleanos, cero o negativos se consideran inválidos para comparación.
- Una superficie en `unknown_surface_m2` no se infiere como terreno ni construcción; queda fuera de la comparación hasta contar con evidencia.
- La cobertura mínima predeterminada es 0.80 del peso comparable y se puede configurar con `estimate(..., min_coverage=...)`. Un anuncio por debajo de ese mínimo queda fuera aunque supere el umbral de similitud.
- La evidencia se clasifica así: 0–1 comparables válidos devuelve `insufficient_comparables` y no devuelve referencia numérica; 2–4 devuelve `provisional` con `evidence_reasons`; 5 o más devuelve `orientative`. Estos umbrales son reglas operativas, no garantías de precisión.
- `candidate_audit` conserva para cada publicación el dato original, su decisión y los motivos. Las publicaciones de un mismo `duplicate_group` se cuentan una vez en estadísticas, pero no se borran: se elige el registro con más campos comparables válidos y, en empate, el `id` lexicográficamente menor. La regla no depende del orden de entrada.
- Las banderas en `price_review_flags` señalan precios que requieren revisión, incluidos los que caen fuera de una banda descriptiva IQR; no los excluyen automáticamente.
- `confidence` es una etiqueta heurística, no una probabilidad ni una medida de precisión: sólo puede ser `medium` para un resultado `orientative`, con similitud promedio de al menos 75 y sin banderas de revisión de precio. No está calibrada con precios de cierre.
- `reference_price_mxn` se calcula con precios anunciados seleccionados; no representa un precio de cierre ni una tasación profesional.

## Métricas descriptivas y advertencias

La salida contiene `price_metrics`, calculada únicamente con los comparables que participan en la estimación. Incluye cantidad, mediana simple, media simple, desviación estándar muestral, coeficiente de variación muestral, mínimo y máximo.

Los cuartiles usan interpolación lineal inclusiva: en una muestra ordenada de tamaño `n`, la posición para el percentil `p` es `(n - 1) × p`. `first_quartile_mxn`, `third_quartile_mxn` e `iqr_mxn` sólo se devuelven con dos o más comparables. La desviación estándar y el coeficiente de variación también son `null` con menos de dos comparables; así se evita presentar una variación inexistente como estadística.

La `reference_price_mxn` continúa siendo una mediana ponderada por similitud. Es distinta de `median_price_mxn`, que es la mediana simple, y de `range_mxn`, que conserva su rango descriptivo histórico P25–P75. Ninguno de estos valores es un intervalo de confianza ni una predicción validada.

`warnings` aporta contexto sin cambiar comparables, referencia, rango, estado ni confianza. Informa de muestra menor a cinco comparables, dispersión alta, banderas de revisión de precio y campos faltantes entre los comparables seleccionados. La advertencia de dispersión usa el parámetro configurable `dispersion_warning_cv`, cuyo valor predeterminado es 0.50; es un umbral heurístico no calibrado, no una regla de precisión estadística.

Todas las métricas describen precios anunciados. No sustituyen precios reales de cierre, una tasación profesional ni una estimación predictiva validada con datos independientes.
