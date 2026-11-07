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

def run():
    values = [
        13, 18, 6, 42, 43, 1, 58, 4,
        7, 32, 8, 59, 9, 64, 38, 37,
        25, 61, 24, 21, 23, 63, 35, 31,
        34, 30, 17, 48, 51, 41, 27, 40,
        15, 33, 46, 2, 28, 44, 54, 56,
        62, 11, 22, 12, 19, 50, 26, 55,
        60, 53, 57, 36, 5, 45, 14, 16,
        20, 39, 47, 10, 3, 52, 29, 49
    ]
    n = len(values)
    i = 0
    j = 0
    temp = 0
    checksum = 0
    k = 0

    while i < n - 1:
        j = 0
        while j < n - i - 1:
            if values[j] > values[j + 1]:
                temp = values[j]
                values[j] = values[j + 1]
                values[j + 1] = temp
            j = j + 1
        i = i + 1

    while k < n:
        checksum = checksum + values[k] * (k + 1)
        k = k + 1
    return checksum


truffleRun = run
