# I115-H10 — Comparación completa de Protos y GraalPy

**Fecha:** 30 de octubre de 2026  
**Producto medido:** Protos experimental I115-H10, campaña completa de 17 workloads  
**Referencia:** GraalPy 25.4.4.1.1, 17 observaciones Tier 2 reutilizadas de su campaña anterior  
**Estado:** cobertura 17/17 para Protos; comparación bilateral de la fase `After TruffleTier`.

> **Objeto del informe.** Se comparan tamaños de grafos del compilador Truffle/Graal, **no** velocidad, latencia, eficiencia energética ni tiempo de compilación. Las capturas Protos H10 y las referencias GraalPy proceden de campañas distintas, aunque comparten los identificadores de workload y fase del grafo. No se ha vuelto a medir GraalPy.

## 1. Alcance, identidad y criterios

- **Protos H10:** campaña en `results/local/i115-h10-all-graphs/` de `guillermomolina/protos-benchmarks`, con `LANGUAGE=protos`, `CASE=all` y `STAGE=reference`. Se ha registrado el total de nodos `relevant_graph_nodes_total_after_truffle_tier`. Los resultados comunicados corresponden a Tier 2.
- **GraalPy:** 25.4.4.1.1. Los totales son los 17 resultados validados de su campaña anterior. No se extrapolan cifras de Protos de revisiones anteriores.
- **Admisión Protos H10:** `VALID_WORKLOADS=17`, `EXPECTED_WORKLOADS=17`, `I115_H10_COMPLETE=True`; los 17 `unit.json` están marcados como válidos y con estabilización `STABLE`. `PRODUCT_IDENTITIES=1`: las capturas comparten revisión y estado de fuentes.
- **Topología de unidades compiladas:** `factorial` y `fibonacci` tienen dos raíces retenidas; los otros 15 casos, una. Se cuenta la suma de unidades *language-owned* que selecciona el harness en cada workload.
- **SHA y versión Maven de H10:** no figuran en el extracto de resultados recibido; por tanto, no se inventan. La identidad completa está en los manifiestos `capture.json` locales.
- **Comparabilidad:** mismas etiquetas de carga y métrica estructural, pero referencias de diferentes campañas. La igualdad de número de raíces no implica identidad del inlining ni equivalencia semántica.

## 2. Matriz completa de los 17 benchmarks — Tier 2

Todas las cifras P y G son **nodos `After TruffleTier`**. Δ = Protos H10 menos GraalPy. Un Δ positivo significa más nodos en H10, no necesariamente mayor tiempo de ejecución.

| Benchmark | Raíces P | Protos H10 (P) | GraalPy (G) | Δ P−G | Δ relativo a G |
|---|---:|---:|---:|---:|---:|
| `factorial` | 2 | **545** | 975 | -430 | -44.1 % |
| `fibonacci` | 2 | **4.141** | 2.865 | +1276 | +44.5 % |
| `method-call` | 1 | **127** | 119 | +8 | +6.7 % |
| `integer-loop` | 1 | **74** | 79 | -5 | -6.3 % |
| `primitive-return-literal` | 1 | **47** | 49 | -2 | -4.1 % |
| `primitive-local-read` | 1 | **47** | 49 | -2 | -4.1 % |
| `primitive-local-write` | 1 | **47** | 49 | -2 | -4.1 % |
| `primitive-integer-add` | 1 | **47** | 49 | -2 | -4.1 % |
| `primitive-object-slot-read` | 1 | **72** | 103 | -31 | -30.1 % |
| `primitive-object-slot-write` | 1 | **122** | 159 | -37 | -23.3 % |
| `primitive-closure-call` | 1 | **106** | 50 | +56 | +112.0 % |
| `primitive-method-call` | 1 | **99** | 82 | +17 | +20.7 % |
| `primitive-if-true` | 1 | **47** | 49 | -2 | -4.1 % |
| `primitive-if-false` | 1 | **47** | 49 | -2 | -4.1 % |
| `primitive-while-zero` | 1 | **47** | 49 | -2 | -4.1 % |
| `primitive-while-once` | 1 | **68** | 73 | -5 | -6.8 % |
| `primitive-while-counted` | 1 | **69** | 74 | -5 | -6.8 % |

**Balance:** Protos H10 tiene menos nodos en **13/17** benchmarks y más en **4/17**; ninguno empata. La suma matemática de los totales de H10 es **5.752**, frente a **4.922** en GraalPy, pero sumar cargas distintas **no** proporciona un índice de rendimiento global ni una métrica de convergencia válida.

## 3. Los cuatro casos en los que H10 supera a GraalPy en nodos

| Prioridad por exceso absoluto | Workload | H10 | GraalPy | Exceso | Exceso relativo |
|---:|---|---:|---:|---:|---:|
| 1 | `fibonacci` | 4.141 | 2.865 | **+1.276** | +44.5 % |
| 2 | `primitive-closure-call` | 106 | 50 | **+56** | +112.0 % |
| 3 | `primitive-method-call` | 99 | 82 | **+17** | +20.7 % |
| 4 | `method-call` | 127 | 119 | **+8** | +6.7 % |

**`fibonacci`** es la diferencia dominante (**+1.276**). Se observan dos unidades compiladas, pero el extracto no incluye sus totales individuales ni histogramas comparados con GraalPy. Por tanto, no puede atribuirse el exceso a la raíz recursiva, a `run`, al tratamiento de capturas o al coste de llamada sin inspección adicional.

**`primitive-closure-call`** aporta **+56** nodos (+112 %): merece un estudio por clase de nodo y por forma física de la invocación antes de cambiar el runtime.

**`primitive-method-call`** aporta **+17** nodos (+20,7 %), y **`method-call`**, **+8** (+6,7 %). Son dos cargas diferentes: no hay que sumar sus deltas como si fueran un único envío de mensaje.

## 4. Rutas con menos nodos que GraalPy

**Atributos de objeto.** `primitive-object-slot-read`: **72** frente a **103** (−31; −30,1 %). `primitive-object-slot-write`: **122** frente a **159** (−37; −23,3 %). Ambas mediciones H10 se estabilizaron con presupuestos **16.000 / 64.000** y una raíz compilada, y su corrección fue `PASS`.

**Recursión factorial.** `factorial`: **545** frente a **975** (−430; −44,1 %), con dos raíces compiladas para Protos. Un menor total AT no permite concluir que el coste por ejecución sea inferior.

**Enteros y locales.** `integer-loop` queda en **74** frente a **79** (−5). Las cuatro primitivas `primitive-return-literal`, `primitive-local-read`, `primitive-local-write` y `primitive-integer-add` registran **47** frente a **49** (−2 cada una).

**Condiciones y bucles.** `primitive-if-true`, `primitive-if-false` y `primitive-while-zero` registran **47** frente a **49** (−2); `primitive-while-once`, **68** frente a **73** (−5); `primitive-while-counted`, **69** frente a **74** (−5).

## 5. Diagnóstico físico específico de H10: lectura y escritura

Se dispone de histogramas por clase de nodo y llamadas residuales para **H10** en los dos benchmarks de atributo. No se han facilitado los histogramas equivalentes de GraalPy de esas mismas unidades; por tanto, este apartado describe H10, sin inventar diferencias por clase frente a GraalPy.

### 5.1 `primitive-object-slot-read` — 72 nodos

| Clase | Nodos H10 |
|---|---:|
| `ConstantNode` | 23 |
| `PiNode` | 7 |
| `FrameState` | 6 |
| `LoadIndexedNode` | 6 |
| `VirtualObjectState` | 5 |
| `FixedGuardNode` | 4 |
| `VirtualArrayNode` | 4 |
| `AllocatedObjectNode` | 1 |
| `CommitAllocationNode` | 1 |
| `IfNode` | 0 |
| `InstanceOfNode` | 0 |
| `InvokeWithExceptionNode` | 0 |

`invoke_targets={}` en la unidad seleccionada. La ausencia observada de `IfNode`, `InstanceOfNode` y `UnboxNode` es coherente con una ruta de lectura especializada, pero no demuestra por sí sola que todas las lecturas del lenguaje utilicen ese camino.

### 5.2 `primitive-object-slot-write` — 122 nodos

| Clase | Nodos H10 |
|---|---:|
| `ConstantNode` | 30 |
| `FrameState` | 22 |
| `FixedGuardNode` | 8 |
| `PiNode` | 8 |
| `VirtualObjectState` | 8 |
| `LoadIndexedNode` | 7 |
| `IfNode` | 1 |
| `InvokeWithExceptionNode` | 1 |
| `RawStoreNode` | 1 |
| `ExceptionObjectNode` | 1 |
| `MethodCallTargetNode` | 1 |

Una llamada Java residual permanece en la unidad de escritura: `ProtosObjectValue.invalidateTrackedLookupDependencies`. **Es un candidato de investigación, no una atribución demostrada de los 22 `FrameState` ni del exceso o defecto respecto a GraalPy.** No se ha observado tal invocación residual en la lectura.

### 5.3 Comportamiento de almacenamiento validado

Los tests focales H10-C comprobaron que la creación y actualizaciones numéricas usan `java.lang.Long` en una ubicación `LongLocation`, también con `2^42` y `Long.MIN_VALUE`. Tras una generalización de la ubicación a objeto y la eliminación/recreación del atributo, Truffle puede conservar `ObjectLocation`; en ese caso se comprueba la lectura mediante el fallback y la proyección guest.

Marcas comunicadas: `I115_H10_C_TRANSITIONS=PASS`, `I115_H10_C_FOCAL_VALIDATION=PASS`. El test confirmó la representación observable `ProtosIntegerValue`. La ruta de almacenamiento de atributos aquí estudiada no necesita estrechar esos enteros a 32 bits.

## 6. Validación y límites de admisión

| Indicador | Resultado aportado |
|---|---|
| Workloads Protos | 17 de 17 |
| Tier seleccionado | 2 en los 17 |
| Estabilización | `STABLE` en los 17 |
| `VALID_WORKLOADS` | `17` |
| `PRODUCT_IDENTITIES` | `1` |
| `I115_H10_COMPLETE` | `True` |
| Referencia GraalPy | 17 valores históricos reutilizados; no recapturados |

Los primeros dos casos de atributos también cuentan con salida explícita de `CAPTURE_INVALID_CASES=0`, `ANALYZE_FAILURES=0` e `INVALID_UNITS=0` en su campaña diagnóstica focal, además de `WORKING_TREE_MATCHES_PRODUCER=YES` y `HEAD_MATCHES_PRODUCER=YES` para los archivos del productor **harness**. Este último par verifica los archivos del productor del harness, **no equivale a demostrar que el código de Protos tenga un checkout limpio**.

La campaña de 17 casos se ejecutó con el mecanismo que permite `--allow-dirty-product` si el árbol de Protos está sucio. El resumen recibido acredita una identidad uniforme y resultados válidos, pero no proporciona el SHA completo del producto o los hashes individuales de cada BGV. Las capturas sobre un producto sucio se deben clasificar como evidencia diagnóstica y no como publicación de una revisión inmutable.

**No disponible para H10:** un barrido sistemático Tier 1, recuentos Final IR para los 17 casos, bytes de código máquina, histogramas completos para los 15 casos restantes, y una medición temporal equiparable. Se omiten, no se sustituyen por cifras de otras revisiones.

Además, la comparación es bilateral: si el harness indica `peer=UNRESOLVED` por falta de GraalJS en el mismo directorio, ello **no invalida** la comparación documental H10–GraalPy, pero impide interpretarla como admisión formal de convergencia trilateral.

## 7. Conclusiones y prioridades de I115-H10

1. **Cobertura completa de H10:** 17 de 17 observaciones estructurales Tier 2 válidas y estables, con una única identidad de producto.
2. **Comparación bilateral:** H10 presenta menos nodos AT en 13 casos y más en cuatro; estos datos no miden velocidad.
3. **Mayor diferencia pendiente:** `fibonacci` (+1.276 nodos). Antes de editar, separar las dos raíces compiladas y comparar sus histogramas con GraalPy.
4. **Segunda prioridad:** `primitive-closure-call` (+56). Después, `primitive-method-call` (+17) y `method-call` (+8).
5. **Atributos:** la lectura y escritura H10 quedan por debajo del tamaño de los grafos de referencia; la escritura mantiene una llamada de invalidación de dependencias, cuya eliminación no debe decidirse sin atribución física y pruebas focales.
6. **Objetivo arquitectónico:** reproducir físicamente las rutas de GraalPy donde resulte útil, documentando las divergencias semánticas de I115, pero sin aumentar ramas, conversiones o materializaciones basándose solo en corrección funcional.

## 8. Fuentes y procedencia

- **Protos H10 (campaña completa local):** `results/local/i115-h10-all-graphs/matrix.json` y `results/local/i115-h10-all-graphs/<workload>/protos/{capture.json,unit.json}` en `guillermomolina/protos-benchmarks`. Los valores de este documento reproducen la tabla `I115_H10_COMPLETE=True` entregada por el mantenedor.
- **Protos H10 (histogramas de atributos):** `results/local/i115-h10-diagnostic/<workload>/protos/unit.json`, junto a BGV, trazas y análisis por unidad, en el mismo repositorio local. Las clases e `invoke_targets` se han tomado del extracto facilitado.
- **GraalPy 25.4.4.1.1:** datos Tier 2 de los 17 casos del [informe completo de la campaña de referencia](https://github.com/guillermomolina/protos-benchmarks/blob/main/reports/I115-H6_vs_H7-R5_Comparacion_completa_Protos_GraalPy.md). Se extrae exclusivamente la **columna de GraalPy**, no cifras de otras revisiones de Protos.
- **Código:** [guillermomolina/protos](https://github.com/guillermomolina/protos). SHA preciso de H10 pendiente de incorporar desde los manifiestos locales.

---

*Informe limitado a Protos I115-H10 y GraalPy; no realiza nuevas mediciones, no atribuye rendimientos temporales y no modifica repositorios.*
