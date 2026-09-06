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

const SOURCE = [
  17, 4, 29, 8, 1, 24, 12, 31,
  6, 20, 15, 3, 27, 10, 32, 14,
  22, 7, 18, 25, 2, 30, 11, 16,
  28, 5, 21, 9, 26, 13, 23, 19,
];
function less(left, right) { return left < right; }
function merge(left, right) {
  const result = [];
  let li = 0;
  let ri = 0;
  while (li < left.length || ri < right.length) {
    if (li === left.length) {
      result.push(right[ri++]);
    } else if (ri === right.length) {
      result.push(left[li++]);
    } else {
      const lv = left[li];
      const rv = right[ri];
      const lr = less(lv, rv);
      const rl = less(rv, lv);
      if (lr && rl) throw new Error("invalid comparator order");
      if (lr) result.push(left[li++]);
      else if (rl) result.push(right[ri++]);
      else result.push(left[li++]);
    }
  }
  return result;
}
function mergeSort(values) {
  if (values.length <= 1) return [...values];
  const middle = Math.floor(values.length / 2);
  return merge(mergeSort(values.slice(0, middle)), mergeSort(values.slice(middle)));
}
export function run() {
  let result = [];
  for (let round = 0; round < 100; round += 1) result = mergeSort(SOURCE);
  return result[0] + result[15] * 100 + result[31] * 10000;
}
if (import.meta.url === `file://${process.argv[1]}`) console.log(run());
