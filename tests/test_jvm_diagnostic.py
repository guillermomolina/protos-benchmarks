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

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "truffle"))

import jvm_diagnostic as diag  # noqa: E402

PRINT = "-Dpolyglot.engine.CompilationFailureAction=Print"
JFR = "-XX:StartFlightRecording=filename=/x/recording.jfr,settings=profile,dumponexit=true"


class ParseTest(unittest.TestCase):
    def test_unset(self):
        self.assertEqual(diag.diagnostic_jvm_options({}), [])

    def test_empty_and_whitespace(self):
        for raw in ("", "   ", "\t\n "):
            self.assertEqual(diag.diagnostic_jvm_options({"DIAGNOSTIC_JVM_OPTIONS": raw}), [])

    def test_one_option(self):
        self.assertEqual(diag.diagnostic_jvm_options({"DIAGNOSTIC_JVM_OPTIONS": PRINT}), [PRINT])

    def test_quoted_option_with_space(self):
        self.assertEqual(
            diag.diagnostic_jvm_options({"DIAGNOSTIC_JVM_OPTIONS": '-Dfoo=bar "-Dbaz=a b"'}),
            ["-Dfoo=bar", "-Dbaz=a b"],
        )


class InsertTest(unittest.TestCase):
    def test_plain_java(self):
        command = ["java", "-cp", "cp", "Main"]
        self.assertEqual(
            diag.insert_java_options(command, [PRINT]),
            ["java", PRINT, "-cp", "cp", "Main"],
        )
        self.assertEqual(command, ["java", "-cp", "cp", "Main"])

    def test_taskset_java(self):
        command = ["taskset", "-c", "3", "java", "-cp", "cp", "Main"]
        self.assertEqual(
            diag.insert_java_options(command, [PRINT]),
            ["taskset", "-c", "3", "java", PRINT, "-cp", "cp", "Main"],
        )

    def test_no_options_is_identity(self):
        command = ["taskset", "-c", "3", "java", "-cp", "cp", "Main"]
        self.assertEqual(diag.insert_java_options(command, []), command)

    def test_coexists_with_jfr(self):
        command = ["taskset", "-c", "3", "java", "-cp", "cp", "Main"]
        result = diag.insert_java_options(command, [JFR] + [PRINT])
        self.assertEqual(result[3:6], ["java", JFR, PRINT])
        self.assertIn(JFR, result)
        self.assertIn(PRINT, result)


class IdentityTest(unittest.TestCase):
    def base(self):
        return {"schema": 4, "definition": "jvm-diagnostic-v4", "diagnostic": "jfr"}

    def test_recorded(self):
        identity = diag.record_jvm_options(self.base(), [PRINT])
        self.assertEqual(identity["diagnostic_jvm_options"], [PRINT])

    def test_empty_recorded(self):
        identity = diag.record_jvm_options(self.base(), [])
        self.assertEqual(identity["diagnostic_jvm_options"], [])

    def test_distinct_options_distinct_key(self):
        none = diag.key(diag.record_jvm_options(self.base(), []))
        printed = diag.key(diag.record_jvm_options(self.base(), [PRINT]))
        other = diag.key(diag.record_jvm_options(self.base(), ["-Dfoo=bar"]))
        self.assertEqual(len({none, printed, other}), 3)

    def test_quoting_variants_same_key(self):
        a = diag.diagnostic_jvm_options({"DIAGNOSTIC_JVM_OPTIONS": "  -Dfoo=bar   '-Dbaz=a b' "})
        b = diag.diagnostic_jvm_options({"DIAGNOSTIC_JVM_OPTIONS": '-Dfoo=bar "-Dbaz=a b"'})
        self.assertEqual(
            diag.key(diag.record_jvm_options(self.base(), a)),
            diag.key(diag.record_jvm_options(self.base(), b)),
        )


if __name__ == "__main__":
    unittest.main()
