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

function makeSet(elements) {
  const result = new Map();
  for (const element of elements) result.set(element, true);
  return result;
}
function union(left, right) {
  const result = new Map();
  for (const element of left.keys()) result.set(element, true);
  for (const element of right.keys()) result.set(element, true);
  return result;
}
function intersection(left, right) {
  const result = new Map();
  for (const element of left.keys()) if (right.has(element)) result.set(element, true);
  return result;
}
function difference(left, right) {
  const result = new Map();
  for (const element of left.keys()) if (!right.has(element)) result.set(element, true);
  return result;
}
export function run() {
  const left = makeSet(Array.from({length: 16}, (_, i) => i + 1));
  const right = makeSet(Array.from({length: 16}, (_, i) => i + 9));
  let unionResult = new Map();
  let intersectionResult = new Map();
  let differenceResult = new Map();
  for (let round = 0; round < 250; round += 1) {
    unionResult = union(left, right);
    intersectionResult = intersection(left, right);
    differenceResult = difference(left, right);
  }
  return unionResult.size * 10000 + intersectionResult.size * 100 + differenceResult.size;
}
if (import.meta.url === `file://${process.argv[1]}`) console.log(run());
