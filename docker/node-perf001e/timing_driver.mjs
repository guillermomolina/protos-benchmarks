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

function lastNonempty(text) {
  const lines = text.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  return lines.length ? lines[lines.length - 1] : "";
}
async function startup(path, expected, samples) {
  for (let i = 1; i <= samples; i += 1) {
    const start = process.hrtime.bigint();
    const child = spawnSync(process.execPath, [`--stack-size=${process.env.PERF001E_NODE_STACK_KB || "32768"}`, path], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    });
    const elapsed = process.hrtime.bigint() - start;
    const actual = lastNonempty(child.stdout || "");
    if (child.status !== 0 || actual !== expected) {
      throw new Error(`startup failed rc=${child.status} expected=${expected} actual=${actual}`);
    }
    console.log(`STARTUP\t${i}\t${elapsed}\t${actual}`);
  }
}
async function execution(path, expected, warmup, steady) {
  const module = await import(pathToFileURL(path).href);
  if (typeof module.run !== "function") throw new Error("workload has no run()");
  for (let i = 1; i <= warmup + steady; i += 1) {
    const start = process.hrtime.bigint();
    const result = module.run();
    const elapsed = process.hrtime.bigint() - start;
    const actual = String(result);
    if (actual !== expected) throw new Error(`result mismatch expected=${expected} actual=${actual}`);
    if (i <= warmup) console.log(`WARMUP\t${i}\t${elapsed}\t${actual}`);
    else console.log(`STEADY\t${i-warmup}\t${elapsed}\t${actual}`);
  }
}
const [mode, path, expected, a, b] = process.argv.slice(2);
if (mode === "startup" && b === undefined) await startup(path, expected, Number(a));
else if (mode === "execution" && b !== undefined) await execution(path, expected, Number(a), Number(b));
else throw new Error("invalid arguments");
