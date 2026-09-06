# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
# DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
# DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
# OF THIS LICENSE AND ITS TERMS, WHETHER OR NOT SUCH RECIPIENT READS THE TERMS OF
# THE LICENSE. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN THE LICENSE. A COPY
# OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED "LICENSE.TXT" ACCOMPANYING
# THE CONTENTS OF THIS FILE. IF A COPY OF THE LICENSE DOES NOT ACCOMPANY THIS
# FILE, A COPY OF THE LICENSE MAY ALSO BE OBTAINED AT THE FOLLOWING WEB SITE:
# https://github.com/guillermomolina/protos-benchmarks
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.

SOURCE = [
    17, 4, 29, 8, 1, 24, 12, 31,
    6, 20, 15, 3, 27, 10, 32, 14,
    22, 7, 18, 25, 2, 30, 11, 16,
    28, 5, 21, 9, 26, 13, 23, 19,
]

def less(left, right):
    return left < right

def merge(left, right):
    result = []
    left_index = 0
    right_index = 0
    while left_index < len(left) or right_index < len(right):
        if left_index == len(left):
            result.append(right[right_index])
            right_index += 1
        elif right_index == len(right):
            result.append(left[left_index])
            left_index += 1
        else:
            left_value = left[left_index]
            right_value = right[right_index]
            lr = less(left_value, right_value)
            rl = less(right_value, left_value)
            if lr and rl:
                raise RuntimeError("invalid comparator order")
            if lr:
                result.append(left_value)
                left_index += 1
            elif rl:
                result.append(right_value)
                right_index += 1
            else:
                result.append(left_value)
                left_index += 1
    return result

def merge_sort(values):
    length = len(values)
    if length <= 1:
        return list(values)
    middle = length // 2
    return merge(merge_sort(values[:middle]), merge_sort(values[middle:]))

def run():
    result = []
    for _ in range(100):
        result = merge_sort(SOURCE)
    return result[0] + result[15] * 100 + result[31] * 10000

if __name__ == "__main__":
    print(run())
