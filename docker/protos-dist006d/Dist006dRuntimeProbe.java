/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
 * DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
 * DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
 * OF THIS LICENSE AND ITS TERMS, WHETHER OR NOT SUCH RECIPIENT READS THE TERMS OF
 * THE LICENSE. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN THE LICENSE. A COPY
 * OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED "LICENSE.TXT" ACCOMPANYING
 * THE CONTENTS OF THIS FILE. IF A COPY OF THE LICENSE DOES NOT ACCOMPANY THIS
 * FILE, A COPY OF THE LICENSE MAY ALSO BE OBTAINED AT THE FOLLOWING WEB SITE:
 * https://github.com/guillermomolina/protos-benchmarks
 *
 * Software distributed under the License is distributed on an "AS IS" basis,
 * WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
 * the specific language governing rights and limitations under the License.
 */

import com.oracle.truffle.api.Truffle;
import org.graalvm.polyglot.Engine;

public final class Dist006dRuntimeProbe {
    private static String text(String value) {
        return value == null ? "" : value;
    }

    public static void main(String[] args) {
        Module truffleModule = Truffle.class.getModule();
        String moduleVersion = "";
        if (truffleModule != null && truffleModule.getDescriptor() != null) {
            moduleVersion = truffleModule.getDescriptor().rawVersion().orElse("");
        }

        try (Engine engine = Engine.create()) {
            System.out.println(
                    "DIST006D_PROBE_RUNTIME_CLASS=" + Truffle.getRuntime().getClass().getName());
            System.out.println("DIST006D_PROBE_ENGINE_VERSION=" + text(engine.getVersion()));
            System.out.println(
                    "DIST006D_PROBE_ENGINE_IMPLEMENTATION=" + text(engine.getImplementationName()));
            System.out.println(
                    "DIST006D_PROBE_TRUFFLE_PACKAGE_VERSION="
                            + text(Truffle.class.getPackage().getImplementationVersion()));
            System.out.println("DIST006D_PROBE_TRUFFLE_MODULE_VERSION=" + moduleVersion);
            System.out.println(
                    "DIST006D_PROBE_JAVA_VERSION=" + text(System.getProperty("java.version")));
            System.out.println(
                    "DIST006D_PROBE_JAVA_RUNTIME_VERSION="
                            + text(System.getProperty("java.runtime.version")));
            System.out.println(
                    "DIST006D_PROBE_JAVA_VM_VERSION=" + text(System.getProperty("java.vm.version")));
            System.out.println(
                    "DIST006D_PROBE_JAVA_VM_VENDOR=" + text(System.getProperty("java.vm.vendor")));
            System.out.println("DIST006D_PROBE_ARCH=" + text(System.getProperty("os.arch")));
        }
    }
}
