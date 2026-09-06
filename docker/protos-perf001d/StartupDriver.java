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

package com.guillermomolina.protos.cli;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public final class StartupDriver {
    private StartupDriver() {}

    private static String lastNonEmptyLine(String text) {
        String result = "";
        for (String line : text.split("\\R")) {
            if (!line.isBlank()) {
                result = line.strip();
            }
        }
        return result;
    }

    private static List<String> childCommand(String mode, String source, String stack) {
        String java =
                ProcessHandle.current()
                        .info()
                        .command()
                        .orElseThrow(() -> new IllegalStateException("cannot locate java executable"));

        List<String> command = new ArrayList<>();
        command.add(java);
        command.add("-Xss" + stack);
        command.add("--enable-native-access=ALL-UNNAMED");
        command.add("-Dpolyglot.engine.AllowExperimentalOptions=true");

        switch (mode) {
            case "interpreter" -> command.add("-Dpolyglot.engine.Compilation=false");
            case "truffle" -> command.add("-Dpolyglot.engine.BackgroundCompilation=false");
            default -> throw new IllegalArgumentException("unsupported mode: " + mode);
        }

        command.add("-cp");
        command.add("/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar");
        command.add("com.guillermomolina.protos.cli.DiagnosticEval");
        command.add(source);
        return command;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 5) {
            throw new IllegalArgumentException(
                    "usage: StartupDriver <mode> <source.protos> <expected> <samples> <stack>");
        }

        String mode = args[0];
        String source = args[1];
        String expected = args[2];
        int samples = Integer.parseInt(args[3]);
        String stack = args[4];
        if (samples <= 0) {
            throw new IllegalArgumentException("samples must be positive");
        }

        List<String> command = childCommand(mode, source, stack);

        for (int i = 1; i <= samples; i++) {
            ProcessBuilder builder = new ProcessBuilder(command);
            // Keep child JVM warnings out of the correctness channel while still
            // retaining the process work itself inside the startup interval.
            builder.redirectError(ProcessBuilder.Redirect.DISCARD);

            long start = System.nanoTime();
            Process process = builder.start();
            byte[] stdoutBytes = process.getInputStream().readAllBytes();
            int rc = process.waitFor();
            long elapsed = System.nanoTime() - start;

            String stdout = new String(stdoutBytes, StandardCharsets.UTF_8);
            String actual = lastNonEmptyLine(stdout);
            if (rc != 0 || !expected.equals(actual)) {
                throw new IllegalStateException(
                        "startup sample failed: rc="
                                + rc
                                + " expected="
                                + expected
                                + " actual="
                                + actual);
            }
            System.out.println("STARTUP\t" + i + "\t" + elapsed + "\t" + actual);
        }
    }
}
