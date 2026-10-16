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
- `candidate_audit` conserva para cada publicación el dato original, su decisión y los motivos. Las publicaciones de un mismo `duplicate_group` se cuentan una vez en estadísticas, pero no se borran ni se confunden anuncios por tener el mismo precio.
- Las banderas en `price_review_flags` señalan precios que requieren revisión, incluidos los que caen fuera de una banda descriptiva IQR; no los excluyen automáticamente.
