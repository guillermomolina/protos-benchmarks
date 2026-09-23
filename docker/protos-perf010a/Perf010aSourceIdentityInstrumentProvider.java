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
 * Hand-written {@link TruffleInstrumentProvider} for {@link Perf010aSourceIdentityInstrument}.
 *
 * <p>Truffle's {@code @TruffleInstrument.Registration} annotation processor normally generates a
 * class shaped exactly like this one (confirmed by inspecting the pinned
 * {@code truffle-api-25.3.4.1.jar}'s own generated
 * {@code com.oracle.truffle.api.debug.impl.DebuggerInstrumentProvider}, which has this identical
 * method shape and is registered the same way); this harness's diagnostic-driver compilation
 * step runs plain {@code javac} with no annotation processor, so this Provider is written by
 * hand instead of generated, and registered manually under
 * {@code META-INF/services/com.oracle.truffle.api.instrumentation.provider.TruffleInstrumentProvider}.
 *
 * <p>{@code TruffleInstrumentProvider} is an abstract class, not an interface (confirmed by
 * inspecting the pinned jar's class file access flags directly - {@code DebuggerInstrumentProvider}
 * itself is a concrete subclass, not an implementation of an interface), so this extends it.
 *
 * <p>The engine reads id/name/version metadata from a {@code @TruffleInstrument.Registration}
 * annotation on the discovered <em>Provider</em> class itself, not from the instrument class
 * {@link #create()} returns - confirmed empirically: without this annotation here, the engine
 * logs "Provider class ... is missing @Registration annotation", silently ignores the
 * instrument, and then fails every later
 * {@code -Dpolyglot.perf010aSourceIdentity=true} invocation with "Could not find option with
 * name perf010aSourceIdentity" (the option is only known once its owning instrument is
 * registered). {@code DebuggerInstrumentProvider} carries this same annotation for the same
 * reason. It is intentionally duplicated onto {@link Perf010aSourceIdentityInstrument} itself
 * too, purely for that class's own readability; only this copy is load-bearing.
 */
@TruffleInstrument.Registration(
        id = Perf010aSourceIdentityInstrument.ID,
        name = "PERF010-A Caller/Helper Source Identity Diagnostic",
        version = "1.0")
public final class Perf010aSourceIdentityInstrumentProvider extends TruffleInstrumentProvider {

    @Override
    public String getInstrumentClassName() {
        return Perf010aSourceIdentityInstrument.class.getName();
    }

    @Override
    public Object create() {
        return new Perf010aSourceIdentityInstrument();
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
