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

import com.oracle.truffle.api.instrumentation.TruffleInstrument;
import com.oracle.truffle.api.instrumentation.provider.TruffleInstrumentProvider;
import java.util.Collection;
import java.util.List;

/**
 * Hand-written {@link TruffleInstrumentProvider} for {@link Perf010aHotRootIdentityInstrument}.
 *
 * <p>Same shape, and the same reasons, as {@link Perf010aSourceIdentityInstrumentProvider}: the
 * diagnostic-driver compilation step runs plain {@code javac} with no annotation processor, so the
 * Provider Truffle's {@code @TruffleInstrument.Registration} processor would generate is written by
 * hand and registered under
 * {@code META-INF/services/com.oracle.truffle.api.instrumentation.provider.TruffleInstrumentProvider}.
 * {@code TruffleInstrumentProvider} is an abstract class, so this {@code extends} it, and the engine
 * reads id/name/version from the {@code @Registration} annotation on this Provider class itself (the
 * copy on the instrument class is only for readability).
 */
@TruffleInstrument.Registration(
        id = Perf010aHotRootIdentityInstrument.ID,
        name = "PERF010-A Hot Root Identity Diagnostic",
        version = "1.0")
public final class Perf010aHotRootIdentityInstrumentProvider extends TruffleInstrumentProvider {

    @Override
    public String getInstrumentClassName() {
        return Perf010aHotRootIdentityInstrument.class.getName();
    }

    @Override
    public Object create() {
        return new Perf010aHotRootIdentityInstrument();
    }

    @Override
    public Collection<String> getServicesClassNames() {
        return List.of();
    }

    @Override
    public List<String> getInternalResourceIds() {
        return List.of();
    }

    @Override
    public Object createInternalResource(String resourceId) {
        throw new IllegalArgumentException(
                "Unsupported internal resource id " + resourceId + ", supported ids are []");
    }
}
