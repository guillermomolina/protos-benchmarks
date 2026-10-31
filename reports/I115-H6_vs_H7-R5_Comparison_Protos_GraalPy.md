# I115-H6 → I115-H7-R5 — Comparación completa de Protos y GraalPy

**Actualización:** 30 de octubre de 2026 · **Estado:** informe comparativo del nuevo corte estructural R5 de los 17 workloads. Protos experimental.

> **Alcance:** recuentos de nodos de los grafos del compilador, **no** rendimiento temporal. Las 34 unidades de la campaña R5 superaron la validación de corrección y estabilización; la comparación H6→R5 es **observacional**, con cambios de procedimiento y de raíces compiladas en algunos casos. No atribuir automáticamente los cambios a un commit concreto.

## 1. Identidad, alcance y validación

- **H6 Protos:** [`493cf1394fd88efa07c5740541a5873d1ba45e44`](https://github.com/guillermomolina/protos/commit/493cf1394fd88efa07c5740541a5873d1ba45e44), `0.3.403-SNAPSHOT`, experimental. La referencia H6 reúne capturas inicialmente admitidas y ocho BGV recuperados *post hoc* cuyo rechazo original sigue vigente.
- **H7-R5 Protos:** [`cb51532254d177dac909021cefb47283f8331a69`](https://github.com/guillermomolina/protos/commit/cb51532254d177dac909021cefb47283f8331a69), rama `I115`, producto preparado como `0.3.403-SNAPSHOT` (no se incrementó la versión del experimento).
- **GraalPy:** 25.4.4.1.1, referencia estructural por workload. Para R5 se volvió a capturar GraalPy en el mismo directorio de campaña.
- **Campaña R5:** `results/local/i115-h7-r5-all-graphs/` del repositorio `guillermomolina/protos-benchmarks`; **17 Protos + 17 GraalPy**, todos con `CORRECTNESS=PASS`, `CAPTURE valid=YES` y `stabilization=STABLE`.
- **Análisis R5:** `ANALYZE_FAILURES=0`, `CASES=34`, `WORKING_TREE_MATCHES_PRODUCER=YES`, `HEAD_MATCHES_PRODUCER=YES`, `INVALID_UNITS=0`.
- **Política:** `STAGE=reference`, fase `After TruffleTier`, presupuesto estable observado Tier 2. Se suman solo las unidades *language-owned* retenidas en **una misma** captura válida por caso y lenguaje; las raíces interpretadas no compiladas quedan fuera.
- **Identidad del harness:** el resultado de verificación confirma coincidencia con el productor; el SHA completo de HEAD, metadatos del host, imagen, CPU y SHA-256 individuales de BGV están en los `capture.json` / `unit.json` **locales**. No se han recibido ni publicado esos archivos, por lo que este documento no inventa sus valores.
- **Tier 1:** el barrido R5 de los 17 casos es una campaña `reference` de Tier 2. **No se ha repetido aquí un Tier 1 sistemático**. No presentar como comparables las cifras Tier 1 H6 de la campaña antigua y resultados R5 Tier 2.

## 2. Matriz completa de los 17 casos — Tier 2

Todas las cifras son nodos **`After TruffleTier`**. H6 procede de su `comparison.csv` histórico; R5 procede del `graphs-summarize` de 34 unidades válidas. Δ = valor R5 menos H6 del mismo lenguaje. **P** = Protos; **G** = GraalPy.

| Workload | H6 P | H6 G | R5 P | R5 G | Δ P | Δ G | R5 P − G |
|---|---:|---:|---:|---:|---:|---:|---:|
| `factorial` | 548 | 975 | **572** | 975 | +24 | 0 | **-403** |
| `fibonacci` | 4.039 | 2.865 | **4.141** | 2.865 | +102 | 0 | **+1.276** |
| `method-call` | 30.698 | 171 | **92** | 119 | -30.606 | -52 | **-27** |
| `integer-loop` | 6.765 | 79 | **74** | 79 | -6.691 | 0 | **-5** |
| `primitive-return-literal` | 47 | 49 | **47** | 49 | 0 | 0 | **-2** |
| `primitive-local-read` | 47 | 49 | **47** | 49 | 0 | 0 | **-2** |
| `primitive-local-write` | 47 | 49 | **47** | 49 | 0 | 0 | **-2** |
| `primitive-integer-add` | 2.444 | 49 | **47** | 49 | -2.397 | 0 | **-2** |
| `primitive-object-slot-read` | 53 | 103 | **66** | 103 | +13 | 0 | **-37** |
| `primitive-object-slot-write` | 135 | 159 | **219** | 159 | +84 | 0 | **+60** |
| `primitive-closure-call` | 222 | 102 | **106** | 50 | -116 | -52 | **+56** |
| `primitive-method-call` | 216 | 134 | **66** | 82 | -150 | -52 | **-16** |
| `primitive-if-true` | 47 | 49 | **47** | 49 | 0 | 0 | **-2** |
| `primitive-if-false` | 47 | 49 | **47** | 49 | 0 | 0 | **-2** |
| `primitive-while-zero` | 47 | 49 | **47** | 49 | 0 | 0 | **-2** |
| `primitive-while-once` | 4.553 | 73 | **68** | 73 | -4.485 | 0 | **-5** |
| `primitive-while-counted` | 4.553 | 74 | **69** | 74 | -4.484 | 0 | **-5** |

**Lectura:** en R5 Protos supera a GraalPy por número de nodos únicamente en **3 de 17** casos; en los otros **14 de 17** el total es menor. No equivale a que Protos sea más rápido: el coste por nodo, el código máquina y el trabajo ejecutado pueden diferir.

## 3. Dónde está hoy el mayor exceso

Ranking bilateral **R5 Protos frente a R5 GraalPy** por exceso absoluto de nodos (no por tiempo de ejecución):

| Orden | Workload | Protos | GraalPy | Exceso | Exceso relativo |
|---:|---|---:|---:|---:|---:|
| 1 | `fibonacci` | 4.141 | 2.865 | **+1.276** | +44.5 % |
| 2 | `primitive-object-slot-write` | 219 | 159 | **+60** | +37.7 % |
| 3 | `primitive-closure-call` | 106 | 50 | **+56** | +112.0 % |

- **`fibonacci` (+1.276):** principal exceso absoluto; dos raíces compiladas en ambos lenguajes. Debe separarse el coste de `run` y de la función recursiva antes de elegir una intervención.
- **`primitive-object-slot-write` (+60):** la señal más clara de incremento relativo a H6 con **una raíz en ambas campañas**; Protos pasa de 135 a 219 nodos (+84; +62,2 %). Requiere reproducción bajo la misma metodología para demostrar regresión.
- **`primitive-closure-call` (+56):** el total de Protos baja (222→106), pero GraalPy baja también (102→50) y el conjunto pasa de dos raíces por lenguaje a una; no hay evidencia de mejora intrínseca de la llamada basada únicamente en esos totales.

## 4. Diferencias H6 → R5 que merecen atención

### 4.1 Posibles regresiones a confirmar

- **`fibonacci`:** Protos **4.039→4.141 (+102; +2,5 %)**; GraalPy **2.865→2.865**. Misma cantidad de raíces (2/2). Es un aumento observado, no una atribución causal al último commit R5.
- **`primitive-object-slot-write`:** Protos **135→219 (+84; +62,2 %)**; GraalPy **159→159**. Misma cantidad de raíces (1/1). Es un candidato especialmente importante para una comparación por revisión.
- **`factorial`:** Protos **548→572 (+24; +4,4 %)**, GraalPy permanece en **975**. Ambos mantienen dos raíces; Protos continúa por debajo en este recuento.
- **`primitive-object-slot-read`:** Protos **53→66 (+13)**, GraalPy **103→103**. Aunque queda por debajo de GraalPy, también ha crecido.

### 4.2 Reducciones observadas, sin prometer una causa común

- **`primitive-method-call`:** Protos **216→66 (−150)**; GraalPy **134→82 (−52)**. Ambas campañas cambian de dos raíces compiladas a una. La **comparación focal R4→R5**, separada más adelante, sí justifica causalmente la desaparición de la materialización en el grafo seleccionado.
- **`primitive-closure-call`:** Protos **222→106 (−116)**; GraalPy **102→50 (−52)**, también con dos→una raíz.
- **`method-call`:** Protos **30.698→92** y GraalPy **171→119**. H6 reunía grandes compilaciones del bucle y algunas recuperaciones; además cambia la cantidad de raíces. **No** interpretar la diferencia bruta como un multiplicador de eficiencia o como una mejora exclusiva de R5.
- **`integer-loop`:** Protos **6.765→74** y GraalPy **79→79**. El resultado antiguo de Protos procedía de una captura cuya admisión original falló. El nuevo resultado es admitido, pero no es una ablation causal por sí sola.
- **`primitive-integer-add`:** Protos **2.444→47**, GraalPy **49→49**. La expansión enorme de H6 ya no figura en R5.
- **`primitive-while-once` y `primitive-while-counted`:** Protos **4.553→68** y **4.553→69**, frente a GraalPy **73** y **74**. Ya no aparecen las expansiones históricas en las capturas actuales.

### 4.3 Topología de raíces compiladas

Cambiar la cantidad de raíces invalida la lectura ingenua de un delta de nodos como ahorro de trabajo en una misma función:

| Workload | H6 P/G | R5 P/G | Interpretación |
|---|---:|---:|---|
| `method-call` | 2/2 | 1/1 | **Topología no equivalente**; comparar las raíces individualmente |
| `primitive-closure-call` | 2/2 | 1/1 | **Topología no equivalente**; comparar las raíces individualmente |
| `primitive-method-call` | 2/2 | 1/1 | **Topología no equivalente**; comparar las raíces individualmente |

`fibonacci` y `factorial` permanecen en **2/2** raíces. Los restantes casos no listados conservan **1/1**. El número igual de raíces es condición útil, pero no garantiza su identidad física ni la equivalencia de inlining.

## 5. Comparación focal controlada R4 → R5: `primitive-method-call`

**Separada de la campaña `reference` de 17 casos.** Estas cifras proceden de capturas frías con el mismo caso, una raíz primaria seleccionada por tier, sin warmup y con idéntico procedimiento de medición R4/R5. La revisión R4 es `bcf01844f495485145b423eaf2a55589fdb580e1`; R5 es `cb51532254d177dac909021cefb47283f8331a69`.

| Métrica | Protos R4 | Protos R5 | GraalPy |
|---|---:|---:|---:|
| Tier 1 — After TruffleTier | 158 | **153** | 181 |
| Tier 1 — Final IR | 295 | **257** | 297 |
| Tier 1 — código máquina | 1.179 B | **1.030 B** | 1.104 B |
| Tier 2 — After TruffleTier | 69 | **66** | 82 |
| Tier 2 — Final IR | 144 | **110** | 135 |
| Tier 2 — código máquina | 614 B | **470 B** | 534 B |

**Atribución física en Tier 2:** `AllocatedObjectNode` **1→0**, `CommitAllocationNode` **1→0**, `VirtualInstanceNode` **2→1** y `BoxNode$AllocatingBoxNode` **0→1** (GraalPy = 1). La ruta admitida ya no materializa `ProtosIntegerValue` en el grafo primario seleccionado.

El commit R5 modifica el retorno del root, la selección en el lowerer y la conversión del host Polyglot. El mantenedor confirmó tests focales **PASS**: `ProtosI115H7MethodCallConvergenceTest` y `ProtosPerf033CanonicalCallableInteropTest`. En I115 se hicieron pruebas focales; **no** se ha afirmado que se ejecutara toda la suite. Esta comprobación no es una medición de velocidad ni una prueba de ausencia absoluta de asignaciones a nivel de máquina.

## 6. Límites de la comparación y evidencia retenida

1. **H6 no es una campaña uniforme y totalmente admitida.** El informe histórico registra BGV recuperados *post hoc* con `ROOT_AMBIGUOUS`, `TIER_COMPILATION_AMBIGUOUS` o `NO_REQUESTED_TIER_BGV_AVAILABLE`. Se reproducen sus cifras históricas, pero no se elevan retroactivamente a capturas válidas.
2. **R5 sí tiene admisión en todos los casos.** Protos y GraalPy reportaron `CAPTURE_INVALID_CASES=0`, estabilización `STABLE` en 17/17 y un `graphs-summarize` con `INVALID_UNITS=0`. Las comprobaciones de productor dieron `WORKING_TREE_MATCHES_PRODUCER=YES` y `HEAD_MATCHES_PRODUCER=YES`.
3. **Falta evidencia por raíz en este documento autónomo.** El resumen de consola proporcionado ofrece la cantidad de raíces y el total por caso, pero no los recuentos individuales ni los histogramas por clase de la nueva campaña. Están en cada `unit.json` local; no se inventan ni se reemplazan por histogramas H6.
4. **Tiempos, Final IR y código máquina de los otros 16 casos:** no se han proporcionado en los resúmenes R5 de esta campaña. No confundir el Total AT con Final IR; no extrapolar el R4→R5 focal de `primitive-method-call` al resto.
5. **El resultado de dos lenguajes no completa la clasificación formal del harness.** `peer=UNRESOLVED` y `FIRST_DIVERGENT_RUNG=NONE` se deben a la ausencia de GraalJS; son compatibles con los recuentos bilaterales válidos. No etiquetar `NONE` como convergencia formal de los tres lenguajes.
6. **Los BGV, las trazas y las exportaciones IGV permanecen locales.** No se han duplicado en este ZIP ni se afirma que sus SHA-256 exactos estén publicados. El informe debe acompañarse, cuando corresponda, de un manifiesto de evidencias derivado directamente de los `unit.json` del host.

## 7. Qué hacer ahora para evitar el efecto péndulo

El problema de alternar mejoras y empeoramientos entre `method-call` y `fibonacci` requiere una disciplina de **regresión transversal por revisión**, no otro parche al primer caso con exceso:

1. **Crear un baseline inmutable de R5 para los 17 workloads**, conservando revision del producto y harness, correctness, `STABLE`, cantidad y papel de raíces, nodos AT, histogramas y BGV SHA-256. Mantener el baseline experimental separado del normativo.
2. **Repetir con un procedimiento idéntico** al menos `fibonacci`, `primitive-object-slot-write`, `primitive-closure-call` y `primitive-method-call` sobre H6, H7-R4 y H7-R5. Comparar raíces equivalentes y mismo tier, sin mezclar recuperaciones H6 y capturas R5 como si fueran la misma serie.
3. **Aislar la primera revisión que causa cada salto** mediante capturas focales antes de tocar el runtime. H6→R5 abarca varias modificaciones del compilador; R4→R5 es solo una de ellas.
4. **Establecer un gate de regresión para futuros slices I115:** todo cambio deberá medir los casos protegidos —idealmente los 17— y justificar explícitamente cualquier aumento, aunque el caso focal mejore. No escoger el siguiente problema por una sola cifra aislada.
5. **No convertir este informe en una decisión normativa.** Las desviaciones semánticas experimentales admitidas para I115 siguen como deuda documentada hasta su reconciliación formal.

## 8. Fuentes y rutas

- [Informe histórico H6](https://github.com/guillermomolina/protos-benchmarks/blob/026a2bd2ed83b42dbe86cf3038661bcd59617833/reports/I115-H6_Comparacion_completa_Protos_GraalPy.md) y [CSV histórico](https://github.com/guillermomolina/protos-benchmarks/blob/ca393f1/results/experiments/i115-h6-2026-10-29/comparison.csv).
- [Recuperaciones H6 y sus histogramas](https://github.com/guillermomolina/protos-benchmarks/tree/ca393f1/results/experiments/i115-h6-2026-10-29/recovery).
- [Commit I115-H7-R5](https://github.com/guillermomolina/protos/commit/cb51532254d177dac909021cefb47283f8331a69).
- [Evidencia duradera de R5 en protos-project-docs](https://github.com/guillermomolina/protos-project-docs/blob/87b4e4276336cefb101150abafd25ce00ac1cabf/docs/project/evidence/I115/I115_H7_R5_METHOD_CALL_COLD_GRAPH_CONVERGENCE_2026_10_30.md).
- **Datos R5 locales:** `results/local/i115-h7-r5-all-graphs/matrix.json` y `results/local/i115-h7-r5-all-graphs/<workload>/<language>/unit.json` para cada una de las 34 unidades; capturas y grafos comprimidos en los directorios de cada caso. `results/local/` se ignora en Git.

---

*Documento nuevo, conservando intacto `reports/I115-H6_Comparacion_completa_Protos_GraalPy.md`. La publicación mediante commit/push del repositorio `protos-benchmarks` sigue siendo una acción del mantenedor.*
