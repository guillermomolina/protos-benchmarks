# I115-H6 — Comparación completa de Protos y GraalPy

**Actualización:** 30 de octubre de 2026 · **Estado:** informe estructural completo con recuperaciones *post hoc*; Protos experimental.

> **Advertencia:** I115-H6 utiliza una implementación experimental de Protos que puede divergir de la semántica normativa. GraalPy 25.4.4.1.1 es la referencia estructural. Los datos describen grafos del compilador, **no** velocidad de ejecución, latencia ni superioridad de un lenguaje.

## 1. Alcance, versiones y lectura de los datos

- **Cobertura:** 17 cargas de trabajo, Protos y GraalPy, Tier 1 y Tier 2: 68 combinaciones carga/lenguaje/tier con al menos una observación numérica. Una observación recuperada no equivale a una captura originalmente admitida.
- **Protos:** `0.3.403-SNAPSHOT`, revisión `493cf1394fd88efa07c5740541a5873d1ba45e44` (I115-H6, experimental).
- **GraalPy:** `25.4.4.1.1`; entorno GraalVM/JDK registrado en las capturas originales y los manifiestos de recuperación.
- **Harness de la campaña inicial:** `b41c60cd368a1fac7509305ea255150d8560a03d`. **Harness de siete recuperaciones posteriores:** `98c9e169ddc0fe3e5b231a4500027157aaa0ae5b` (solo añadía artefactos de publicación, sin cambios del productor). Una recuperación Tier 2 reutiliza la captura inicial.
- **Publicación original:** [I115-H6, commit de publicación `98c9e16`](https://github.com/guillermomolina/protos-benchmarks/tree/98c9e169ddc0fe3e5b231a4500027157aaa0ae5b/results/experiments/i115-h6-2026-10-29). **Recuperaciones:** [commit `ca393f1`](https://github.com/guillermomolina/protos-benchmarks/tree/ca393f1/results/experiments/i115-h6-2026-10-29/recovery).
- **DSL:** número estático de instrucciones Bytecode DSL del `run` guest; no es un contador dinámico de operaciones ejecutadas. **AT:** nodos del IR en la fase `After TruffleTier`; **IR:** nodos `Final IR`. **Tier:** compilación observada; **guest roots:** raíces realmente compiladas, no totalidad de raíces interpretadas.
- **O:** resultado originalmente publicado y admitido para esa(s) raíz(ces). **R:** BGV recuperado *post hoc*, con nodos comprobados contra la traza, pero procedente de captura cuya admisión original fue negativa. Una celda no marcada se obtiene de los CSV originales. Las cifras `O + R` son **observaciones separadas, no una suma válida**.

## 2. Matriz completa de los 17 benchmarks

Las celdas Tier indican **AT / IR**, en nodos. P = Protos experimental; G = GraalPy. En `method-call` Tier 1 se presentan separadamente dos raíces por lenguaje; no pueden agregarse como un mismo conjunto de compilación.

| Benchmark | DSL P/G | Tier 1 P (AT / IR) | Tier 1 G (AT / IR) | Tier 2 P (AT / IR) | Tier 2 G (AT / IR) |
|---|---:|---:|---:|---:|---:|
| `factorial` | 20 / 20 | 290 / 551 | 377 / 749 | 548 / 1.100 | 975 / 1.565 |
| `fibonacci` | 20 / 20 | 393 / 940 | 389 / 851 | 4.039 / 15.932 | 2.865 / 5.637 |
| `method-call` | 2.348 / 64 | 130/162 (O) + 30.726/71.304 (R) | 109/156 (O) + 267/494 (R) | 30.698 / 50.501 | 171 / 306 |
| `integer-loop` | 1.102 / 52 | 6.864 / 14.291 **R** | 187 / 272 **R** | 6.765 / 4.334 **R** | 79 / 144 |
| `primitive-return-literal` | 16 / 16 | 104 / 122 | 106 / 126 | 47 / 59 | 49 / 62 |
| `primitive-local-read` | 20 / 20 | 104 / 122 | 106 / 126 | 47 / 59 | 49 / 62 |
| `primitive-local-write` | 24 / 24 | 104 / 122 | 106 / 126 | 47 / 59 | 49 / 62 |
| `primitive-integer-add` | 382 / 28 | 2.503 / 5.281 **R** | 106 / 126 | 2.444 / 279 | 49 / 62 |
| `primitive-object-slot-read` | 18 / 18 | 110 / 137 | 162 / 260 | 53 / 71 | 103 / 171 |
| `primitive-object-slot-write` | 46 / 24 | 194 / 351 | 218 / 319 | 135 / 256 | 159 / 132 |
| `primitive-closure-call` | 28 / 32 | 395 / 798 | 271 / 512 | 222 / 417 | 102 / 158 |
| `primitive-method-call` | 20 / 28 | 383 / 715 | 290 / 453 | 216 / 443 | 134 / 224 |
| `primitive-if-true` | 28 / 28 | 104 / 122 | 106 / 126 | 47 / 59 | 49 / 62 |
| `primitive-if-false` | 24 / 20 | 104 / 122 | 106 / 126 | 47 / 59 | 49 / 62 |
| `primitive-while-zero` | 26 / 22 | 104 / 122 | 106 / 126 | 47 / 59 | 49 / 62 |
| `primitive-while-once` | 738 / 40 | 4.652 / 9.706 **R** | 181 / 261 | 4.553 / 2.635 | 73 / 62 |
| `primitive-while-counted` | 738 / 40 | 4.652 / 9.707 **R** | 182 / 262 | 4.553 / 2.951 | 74 / 62 |

**Notas de la matriz:**

1. `method-call`, Tier 1: el CSV original contiene solo la raíz guest pequeña de Protos (**130 / 162**) y una raíz de GraalPy (**109 / 156**). La recuperación añadió la raíz grande de Protos (**30.726 / 71.304**) y `run` de GraalPy (**267 / 494**). Son ejecuciones distintas. Los originales no deben sustituirse ni combinarse mediante una suma como si fueran una única captura.
2. `method-call`, Tier 2: se muestran los **totales de dos raíces guest observadas en la campaña original**: Protos **30.698 / 50.501**; GraalPy **171 / 306**. La comparación de conjuntos de raíces no demuestra identidad funcional entre todas sus partes.
3. `integer-loop`, Tier 2 Protos: **6.765 / 4.334** procede del BGV de la compilación `2818` recuperado de **la propia captura original inválida** (`NO_REQUESTED_TIER_BGV_AVAILABLE`). GraalPy Tier 2 (**79 / 144**) procede del CSV original.
4. Los demás valores marcados **R** provienen de capturas nuevas con BGV verificado. No se han alterado los CSV originales. En particular, `primitive-integer-add` Tier 1 Protos tiene Final IR **5.281** en la recuperación, aunque la traza de la ejecución inicial mostraba **5.258**; se conserva el dato correspondiente a cada ejecución.
5. Las filas con varias raíces admitidas (`factorial`, `fibonacci`, `primitive-closure-call`, `primitive-method-call`, y `method-call` Tier 2) conservan el criterio de agregación del CSV original. La recuperación añade observaciones de raíces sin reabrir la admisión original.

## 3. Registro de las ocho recuperaciones BGV

Cada recuperación tiene conteo de nodos concordante con el BGV analizado, ID de compilación, SHA-256 del BGV y metadatos de captura publicados como **resúmenes**. Ningún BGV, `trace.log` ni exportación IGV grande se ha subido a GitHub.

| Caso | Lenguaje | Tier | CallTarget | ID de compilación | AT | Final IR | Código máquina (bytes) | Motivo de rechazo de captura |
|---|---|---:|---|---:|---:|---:|---:|---|
| `method-call` | Protos | 1 | `1:5` | `2951` | 30.726 | 71.304 | 353.992 | `ROOT_AMBIGUOUS` |
| `method-call` | GraalPy | 1 | `1:467` | `5129` | 267 | 494 | 2.864 | `TIER_COMPILATION_AMBIGUOUS` |
| `integer-loop` | Protos | 1 | `1:2` | `2753` | 6.864 | 14.291 | 67.379 | `TIER_COMPILATION_AMBIGUOUS` |
| `integer-loop` | GraalPy | 1 | `1:466` | `4863` | 187 | 272 | 1.238 | `TIER_COMPILATION_AMBIGUOUS` |
| `integer-loop` | Protos | 2 | `1:2` | `2818` | 6.765 | 4.334 | 21.175 | `NO_REQUESTED_TIER_BGV_AVAILABLE` |
| `primitive-integer-add` | Protos | 1 | `1:2` | `2692` | 2.503 | 5.281 | 22.920 | `TIER_COMPILATION_AMBIGUOUS` |
| `primitive-while-once` | Protos | 1 | `1:2` | `2683` | 4.652 | 9.706 | 44.093 | `TIER_COMPILATION_AMBIGUOUS` |
| `primitive-while-counted` | Protos | 1 | `1:2` | `2687` | 4.652 | 9.707 | 44.717 | `TIER_COMPILATION_AMBIGUOUS` |

**Integridad:** [recovered-nodes.csv](https://github.com/guillermomolina/protos-benchmarks/blob/ca393f1/results/experiments/i115-h6-2026-10-29/recovery/recovered-nodes.csv) contiene los SHA-256 de los BGV y trazas y las revisiones productoras; [node-histograms.csv](https://github.com/guillermomolina/protos-benchmarks/blob/ca393f1/results/experiments/i115-h6-2026-10-29/recovery/node-histograms.csv) detalla **467** filas de clases de nodos. Los archivos originales siguen en almacenamiento local. Todos los BGV se verificaron contra las trazas; sus capturas continúan marcadas como inválidas por los criterios de admisión originales.

## 4. Lectura comparativa de todos los casos

### 4.1 Recursión

- **`factorial`:** el DSL `run` empata (20/20). Tier 1: Protos 290 frente a GraalPy 377 AT; Tier 2: **548 frente a 975** AT. En esta carga, Protos tiene el grafo Tier 2 observado más pequeño; no implica mayor velocidad.
- **`fibonacci`:** DSL 20/20; Tier 1 prácticamente empata en AT (393/389). Tier 2: Protos **4.039 / 15.932** frente a GraalPy **2.865 / 5.637**; la diferencia crece tras optimizar, especialmente en Final IR.

### 4.2 Acceso a variables, literales y aritmética

- **`primitive-return-literal`:** DSL 16/16; Tier 2 AT **47/49**, diferencia de dos nodos. Tier 1 también es próximo: 104/106.
- **`primitive-local-read`:** DSL 20/20; comparte los recuentos 104/106 en Tier 1 y 47/49 en Tier 2.
- **`primitive-local-write`:** DSL 24/24; comparte los mismos recuentos de grafos que las dos primitivas anteriores.
- **`primitive-integer-add`:** DSL Protos **382** frente a **28** GraalPy; Tier 1 recuperado **2.503/5.281** frente a **106/126**; Tier 2 **2.444/279** frente a **49/62**. La diferencia señala una ruta de suma considerablemente más compleja a nivel de compilador.
- **`primitive-object-slot-read`:** DSL 18/18; Tier 2 Protos **53/71** frente a GraalPy **103/171**. Aquí Protos presenta menos nodos.
- **`primitive-object-slot-write`:** DSL 46/24; Tier 2 Protos **135/256** frente a GraalPy **159/132**. Protos tiene menos nodos AT pero más nodos Final IR; las dos fases deben interpretarse por separado.

### 4.3 Llamadas

- **`primitive-closure-call`:** DSL 28/32; Tier 2 **222/417** frente a **102/158**, aproximadamente **2,18×** en AT. Es una brecha moderada frente a las rutas con bucles.
- **`primitive-method-call`:** DSL 20/28; Tier 2 **216/443** frente a **134/224**, aproximadamente **1,61×** en AT. No debe confundirse con la carga `method-call` de 1.000 iteraciones.
- **`method-call`:** DSL **2.348/64**; Tier 1 raíz grande recuperada Protos **30.726** AT frente a `run` recuperado de GraalPy **267**, unas **115×** en el tamaño de esos grafos individuales; las otras dos raíces Tier 1 aparecen por separado en la matriz. Tier 2, sumando las raíces originalmente admitidas dentro de cada lenguaje, **30.698** frente a **171** AT. Las raíces de distintos lenguajes no están necesariamente alineadas uno a uno y no puede concluirse que esos cocientes sean directamente sobrecostes de un envío de método aislado.

### 4.4 Control de flujo y bucles

- **`primitive-if-true`:** DSL 28/28; Tier 2 **47/59** Protos frente a **49/62** GraalPy, prácticamente igual tamaño.
- **`primitive-if-false`:** DSL 24/20; Tier 2 **47/59** frente a **49/62**, misma proximidad estructural.
- **`primitive-while-zero`:** DSL 26/22; Tier 2 **47/59** frente a **49/62**, consistente con la simplificación de la rama no ejecutada.
- **`primitive-while-once`:** DSL **738/40**; Tier 1 recuperado Protos **4.652/9.706** frente a GraalPy **181/261**; Tier 2 **4.553/2.635** frente a **73/62**. Brecha Tier 2 AT de unas **62×**.
- **`primitive-while-counted`:** DSL **738/40**; Tier 1 recuperado **4.652/9.707** frente a **182/262**; Tier 2 **4.553/2.951** frente a **74/62**. Brecha Tier 2 AT de unas **62×**.
- **`integer-loop`:** DSL **1.102/52**; Tier 1 recuperado Protos **6.864/14.291** y GraalPy **187/272**; Tier 2 Protos recuperado **6.765/4.334** frente a GraalPy original **79/144**, unas **86×** en AT. La captura Tier 2 de Protos estaba originalmente rechazada por múltiples compilaciones del mismo tier.

## 5. Diagnóstico físico basado en histogramas recuperados

Los histogramas recuperados permiten describir **qué clases de nodos ocupan el grafo**, pero **no atribuir causalidad** sin examinar las rutas y las operaciones que los generan:

| Grafo recuperado | `FrameState` | `BeginNode` | `EndNode` | `IfNode` | `InstanceOfNode` | AT total |
|---|---:|---:|---:|---:|---:|---:|
| method-call/Protos T1 | 6.084 | 3.855 | 2.730 | 1.847 | 1.205 | 30.726 |
| method-call/GraalPy T1 | 46 | 15 | 8 | 7 | — | 267 |
| integer-loop/Protos T1 | 1.205 | 902 | 625 | 455 | 375 | 6.864 |
| integer-loop/Protos T2 | 1.186 | 889 | 618 | 449 | 375 | 6.765 |
| primitive-integer-add/Protos T1 | 459 | 309 | 216 | 156 | 127 | 2.503 |
| primitive-while-once/Protos T1 | 799 | 618 | 427 | 311 | 252 | 4.652 |
| primitive-while-counted/Protos T1 | 799 | 618 | 427 | 311 | 252 | 4.652 |

**Nota:** «—» significa que el valor de `InstanceOfNode` no se incluye en este extracto, no que su recuento sea necesariamente cero. El CSV de histogramas es la fuente completa por clase.

En `method-call/Protos` Tier 1 se contabilizan además **1.627 `FixedGuardNode`**, **1.551 `LoadFieldNode`**, **1.255 `IsNullNode`**, **1.766 `PiNode`** y **919 `RawStoreNode`**. Esta composición sugiere investigar la materialización del marco, las lecturas/capturas de variables, las comprobaciones de tipos y el control de flujo del bucle, sin concluir todavía cuál es la causa principal. Las llamadas simples y las condiciones constantes ya presentan grafos comparables a GraalPy, por lo que una hipótesis amplia de «sobrecoste inevitable de todo envío» no está respaldada por todos los casos.

## 6. Estabilidad de compilación y límites de admisión

Las trazas iniciales mostraron `uncommon trap` y recompilación de raíces antes de la versión final observada:

- `primitive-integer-add/protos`: 103 AT → invalidación → 2.503 AT.
- `integer-loop/protos`: 103 AT → invalidación → 103 AT → invalidación → 6.864 AT (Tier 1) → 6.765 AT (Tier 2 en la traza inicial).
- `method-call/protos`, raíz grande: 103 AT → invalidación → 30.726 AT Tier 1; su expansión ya está presente antes de Tier 2.

La regla original del harness exigía una única compilación por CallTarget/tier; varias compilaciones producían `TIER_COMPILATION_AMBIGUOUS`. Una recuperación selecciona la última compilación registrada de ese tier únicamente cuando su BGV es único para el ID elegido, no hay invalidaciones/fallos posteriores en la traza disponible y los nodos AT extraídos del BGV coinciden con la traza. Esto **no** establece estabilidad entre ejecuciones, ni revoca el fallo de admisión de la captura original. Los valores recuperados, incluso cuando proceden de la captura original, se etiquetan por separado.

## 7. Conclusiones y próximas prioridades

1. **Cobertura numérica completa:** ya existe evidencia de nodos para las 68 combinaciones caso/lenguaje/tier; ocho BGV anteriormente excluidos fueron recuperados y validados como observaciones *post hoc*. No todas las capturas cumplen la política original de admisión.
2. **Las primitivas básicas convergen parcialmente:** literales, variables locales, condiciones constantes y lectura de slots muestran grafos Tier 2 cercanos o menores que GraalPy en AT. Por tanto, las brechas se concentran en determinadas rutas y no afectan uniformemente a todos los casos.
3. **Prioridad física principal:** `method-call`, `integer-loop`, `primitive-while-once`, `primitive-while-counted` y `primitive-integer-add`, donde persisten grandes expansiones. Revisar Bytecode DSL, cierres/capturas, materialización y guardas; separar los costes del bucle de los del envío de métodos.
4. **Comparaciones por raíz, no rankings:** `method-call` mezcla raíces guest distintas y algunas recuperaciones son de JVM diferentes. Los cocientes de nodos son descripciones de grafo y nunca multiplicadores de tiempo de ejecución.
5. **Publicación ligera y trazable:** el commit `ca393f1` publica solo resúmenes e histogramas, no los 1,2 GB de análisis IGV ni los BGV. Las capturas y sus hashes permanecen identificadas en los manifiestos locales/publicados.

## 8. Fuentes y procedencia

- [Resultados originales: `comparison.csv`](https://github.com/guillermomolina/protos-benchmarks/blob/ca393f1/results/experiments/i115-h6-2026-10-29/comparison.csv).
- [Métricas originales de Protos: `protos/nodes.csv`](https://github.com/guillermomolina/protos-benchmarks/blob/ca393f1/results/experiments/i115-h6-2026-10-29/protos/nodes.csv).
- [Métricas originales de GraalPy: `graalpy/nodes.csv`](https://github.com/guillermomolina/protos-benchmarks/blob/ca393f1/results/experiments/i115-h6-2026-10-29/graalpy/nodes.csv).
- [Nodos recuperados: `recovery/recovered-nodes.csv`](https://github.com/guillermomolina/protos-benchmarks/blob/ca393f1/results/experiments/i115-h6-2026-10-29/recovery/recovered-nodes.csv).
- [Histogramas recuperados: `recovery/node-histograms.csv`](https://github.com/guillermomolina/protos-benchmarks/blob/ca393f1/results/experiments/i115-h6-2026-10-29/recovery/node-histograms.csv).
- [Manifiesto de recuperación: `recovery/manifest.json`](https://github.com/guillermomolina/protos-benchmarks/blob/ca393f1/results/experiments/i115-h6-2026-10-29/recovery/manifest.json).
- [README de metodología y limitaciones de la campaña](https://github.com/guillermomolina/protos-benchmarks/blob/ca393f1/results/experiments/i115-h6-2026-10-29/README.md).

