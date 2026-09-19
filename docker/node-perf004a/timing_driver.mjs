// THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
// ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
// DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
// DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
// OF THIS LICENSE AND ITS TERMS, WHETHER OR NOT SUCH RECIPIENT READS THE TERMS OF
// THE LICENSE. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN THE LICENSE. A COPY
// OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED "LICENSE.TXT" ACCOMPANYING
// THE CONTENTS OF THIS FILE. IF A COPY OF THE LICENSE DOES NOT ACCOMPANY THIS
// FILE, A COPY OF THE LICENSE MAY ALSO BE OBTAINED AT THE FOLLOWING WEB SITE:
// https://github.com/guillermomolina/protos-benchmarks
//
// Software distributed under the License is distributed on an "AS IS" basis,
// WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
// the specific language governing rights and limitations under the License.

import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

function lastNonemptyLine(text) {
  const lines = String(text || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  return lines.length ? lines[lines.length - 1] : "";
}

async function startup(path, expected, samples) {
  if (!Number.isInteger(samples) || samples <= 0) throw new Error("samples must be positive");
  const values = [];
  const stack = process.env.PERF004A_NODE_STACK_KB || "32768";
  for (let index = 0; index < samples; index += 1) {
    console.error(`STARTUP_SAMPLE_BEGIN index=${index + 1}/${samples}`);
    const started = process.hrtime.bigint();
    const child = spawnSync(
      process.execPath,
      [`--stack-size=${stack}`, path],
      { encoding: "utf8", timeout: 120000, stdio: ["ignore", "pipe", "pipe"] },
    );
    const elapsed = process.hrtime.bigint() - started;
    const actual = lastNonemptyLine(child.stdout);
    if (child.error || child.status !== 0 || actual !== expected) {
      throw new Error(
        `startup failed status=${child.status} expected=${expected} actual=${actual} ` +
        `error=${child.error || ""} stderr=${String(child.stderr || "").slice(-4000)}`,
      );
    }
    if (elapsed <= 0n) throw new Error("non-positive startup sample");
    values.push(Number(elapsed));
    console.error(`STARTUP_SAMPLE_PASS index=${index + 1}/${samples} elapsed_ns=${elapsed}`);
  }
  console.log(JSON.stringify({
    schema_version: 1,
    runtime: "javascript",
    expected,
    fresh_process_per_sample: true,
    docker_start_outside_timing: true,
    startup_ns: values,
  }));
}

async function execution(path, expected, warmup, steady) {
  if (!Number.isInteger(warmup) || warmup < 0 || !Number.isInteger(steady) || steady < 0) {
    throw new Error("iteration counts must be non-negative");
  }
  const module = await import(pathToFileURL(path).href);
  if (typeof module.run !== "function") throw new Error(`workload has no callable run(): ${path}`);
  const warmupNs = [];
  const steadyNs = [];
  for (const [phase, count, target] of [
    ["warmup", warmup, warmupNs],
    ["steady", steady, steadyNs],
  ]) {
    for (let index = 0; index < count; index += 1) {
      const started = process.hrtime.bigint();
      const result = module.run();
      const elapsed = process.hrtime.bigint() - started;
      const actual = String(result);
      if (actual !== expected) {
        throw new Error(`${phase}[${index}] result mismatch expected=${expected} actual=${actual}`);
      }
      if (elapsed <= 0n) throw new Error(`non-positive ${phase} sample`);
      target.push(Number(elapsed));
    }
  }
  console.log(JSON.stringify({
    schema_version: 1,
    runtime: "javascript",
    expected,
    module_reused: true,
    run_binding_reused: true,
    warmup_ns: warmupNs,
    steady_ns: steadyNs,
  }));
}

const [mode, path, expected, a, b] = process.argv.slice(2);
if (mode === "startup" && b === undefined) {
  await startup(path, expected, Number(a));
} else if (mode === "execution" && b !== undefined) {
  await execution(path, expected, Number(a), Number(b));
} else {
  throw new Error("invalid arguments");
}
