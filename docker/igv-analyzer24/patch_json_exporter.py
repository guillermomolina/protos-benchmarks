#!/usr/bin/env python3
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

path = Path(
    "/opt/graal/visualizer/IdealGraphVisualizer/JSONExporter/"
    "src/org/graalvm/visualizer/JSONExporter.java"
)
text = path.read_text(encoding="utf-8")

import_anchor = "import java.nio.file.Paths;\n"
if import_anchor not in text:
    raise SystemExit("IGV exporter import anchor not found")
text = text.replace(
    import_anchor,
    import_anchor
    + "import java.nio.charset.StandardCharsets;\n"
    + "import java.util.UUID;\n",
    1,
)

method_start_marker = "    private static String createFileName("
next_method_marker = "    private static JSONHelper.JSONObjectBuilder stacktrace("
try:
    method_start = text.index(method_start_marker)
    next_method = text.index(next_method_marker, method_start)
except ValueError as exc:
    raise SystemExit(f"IGV exporter method boundary not found: {exc}")

new_method = r'''    private static String createFileName(String graphType, String graphName, int part) {
        String p = (part == -1) ? "" : ("." + part);
        String gt = graphType.replaceAll("[^\\p{Alnum}]", "");
        String gn = graphName.replaceAll("[^\\p{Alnum}]", "_");
        String identity = graphType + "\u0000" + graphName;
        String fingerprint = UUID.nameUUIDFromBytes(identity.getBytes(StandardCharsets.UTF_8))
                .toString().replace("-", "");

        // Keep physical filenames safely below common NAME_MAX=255 limits.
        // Complete graph identity remains in the JSON name/graph_type fields.
        if (gt.length() > 48) {
            gt = gt.substring(0, 48);
        }
        if (gn.length() > 96) {
            gn = gn.substring(0, 96);
        }
        return gt + "_" + gn + "_" + fingerprint + p + ".json";
    }

'''

text = text[:method_start] + new_method + text[next_method:]

for required in (
    "UUID.nameUUIDFromBytes",
    "gt.length() > 48",
    "gn.length() > 96",
    'return gt + "_" + gn + "_" + fingerprint + p + ".json";',
):
    if required not in text:
        raise SystemExit(f"patched exporter verification failed: {required}")

path.write_text(text, encoding="utf-8")
