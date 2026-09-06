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

def make_set(elements):
    result = {}
    for element in elements:
        result[element] = True
    return result

def union(left, right):
    result = {}
    for element in left:
        result[element] = True
    for element in right:
        result[element] = True
    return result

def intersection(left, right):
    result = {}
    for element in left:
        if element in right:
            result[element] = True
    return result

def difference(left, right):
    result = {}
    for element in left:
        if element not in right:
            result[element] = True
    return result

def run():
    left = make_set(range(1, 17))
    right = make_set(range(9, 25))
    union_result = {}
    intersection_result = {}
    difference_result = {}
    for _ in range(250):
        union_result = union(left, right)
        intersection_result = intersection(left, right)
        difference_result = difference(left, right)
    return len(union_result) * 10000 + len(intersection_result) * 100 + len(difference_result)

if __name__ == "__main__":
    print(run())
