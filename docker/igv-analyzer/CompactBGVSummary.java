/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
 * DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
 * DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
 * OF THIS LICENSE AND ITS TERMS, WHETHER OR NOT SUCH RECIPIENT READS THE TERMS OF
 * THE LICENSE. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN THE LICENSE. A COPY
 * OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED "LICENSE.TXT" ACCOMPANYING
 * THE CONTENTS OF THIS FILE. IF A COPY OF THE LICENSE DOES NOT ACCOMPANY THIS
 * FILE, A COPY OF THE LICENSE MAY ALSO BE OBTAINED AT:
 * https://github.com/guillermomolina/protos-benchmarks
 *
 * Software distributed under the License is distributed on an "AS IS" basis,
 * WITHOUT WARRANTY OF ANY KIND, either express or implied.
 */

package com.guillermomolina.protos.benchmarks.igv;

import java.io.BufferedInputStream;
import java.io.BufferedWriter;
import java.security.DigestInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.graalvm.visualizer.data.GraphDocument;
import org.graalvm.visualizer.data.InputEdge;
import org.graalvm.visualizer.data.InputGraph;
import org.graalvm.visualizer.data.InputNode;
import org.graalvm.visualizer.data.Property;
import org.graalvm.visualizer.data.serialization.BinaryReader;
import org.graalvm.visualizer.data.serialization.ModelBuilder;
import org.graalvm.visualizer.data.serialization.StreamSource;
import org.graalvm.visualizer.data.src.LocationStackFrame;
import org.graalvm.visualizer.data.src.LocationStratum;

public final class CompactBGVSummary {
    private static final String NAME = "name";

    private CompactBGVSummary() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 2 || !args[0].endsWith(".bgv")) {
            System.err.println("usage: bgv-summary <file.bgv> <output.ndjson> [term...]");
            System.exit(2);
        }

        Path input = Paths.get(args[0]);
        Path output = Paths.get(args[1]);
        List<String> terms = new ArrayList<>();
        for (int i = 2; i < args.length; i++) {
            if (!args[i].isEmpty()) {
                terms.add(args[i]);
            }
        }

        Map<String, Long> counts = new LinkedHashMap<>();
        for (String term : terms) {
            counts.put(term, 0L);
        }

        List<InputGraph> graphs = new ArrayList<>();
        String sourceSha = fillGraphsList(input, graphs);
        long sourceSize = Files.size(input);

        Path parent = output.toAbsolutePath().getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }

        long graphCount = 0;
        long nodeCount = 0;
        long edgeCount = 0;

        try (BufferedWriter out = Files.newBufferedWriter(output, StandardCharsets.UTF_8)) {
            out.write("{\"kind\":\"source\",\"source\":");
            out.write(quote(args[0]));
            out.write(",\"size_bytes\":");
            out.write(Long.toString(sourceSize));
            out.write(",\"sha256\":");
            out.write(quote(sourceSha));
            out.write("}\n");

            for (InputGraph graph : graphs) {
                if (graph.getProperties().size() <= 1) {
                    continue;
                }

                String graphName = graph.getProperties().get(NAME, String.class);
                if (graphName == null) {
                    graphName = "";
                }
                String graphType = graph.getGraphType();
                if (graphType == null) {
                    graphType = "";
                }

                countText(counts, graphName);
                countText(counts, graphType);

                long localNodes = 0;
                for (InputNode node : graph.getNodes()) {
                    localNodes++;
                    for (Property<?> property : node.getProperties()) {
                        countText(counts, property.getName());
                        Object value = property.getValue();
                        if (value instanceof LocationStackFrame) {
                            countStack(counts, (LocationStackFrame) value);
                        } else if (value != null) {
                            countText(counts, String.valueOf(value));
                        }
                    }
                }

                long localEdges = 0;
                for (InputEdge edge : graph.getEdges()) {
                    localEdges++;
                    countText(counts, String.valueOf(edge.getLabel()));
                    countText(counts, String.valueOf(edge.getType()));
                }

                graphCount++;
                nodeCount += localNodes;
                edgeCount += localEdges;

                out.write("{\"kind\":\"graph\",\"dump_id\":");
                out.write(Integer.toString(graph.getDumpId()));
                out.write(",\"graph_type\":");
                out.write(quote(graphType));
                out.write(",\"graph_name\":");
                out.write(quote(graphName));
                out.write(",\"nodes\":");
                out.write(Long.toString(localNodes));
                out.write(",\"edges\":");
                out.write(Long.toString(localEdges));
                out.write("}\n");
            }

            for (Map.Entry<String, Long> entry : counts.entrySet()) {
                out.write("{\"kind\":\"term\",\"term\":");
                out.write(quote(entry.getKey()));
                out.write(",\"occurrences\":");
                out.write(Long.toString(entry.getValue()));
                out.write("}\n");
            }

            out.write("{\"kind\":\"totals\",\"graphs\":");
            out.write(Long.toString(graphCount));
            out.write(",\"nodes\":");
            out.write(Long.toString(nodeCount));
            out.write(",\"edges\":");
            out.write(Long.toString(edgeCount));
            out.write(",\"terms\":");
            out.write(Integer.toString(counts.size()));
            out.write("}\n");
        }

        System.out.println(
            "COMPACT_BGV_SUMMARY: PASS graphs=" + graphCount
            + " nodes=" + nodeCount
            + " edges=" + edgeCount
            + " terms=" + counts.size()
        );
    }

    private static String fillGraphsList(Path input, List<InputGraph> graphs)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        ModelBuilder mb = new ModelBuilder(new GraphDocument(), null, null) {
            @Override
            public InputGraph startGraph(int dumpId, String format, Object[] args) {
                InputGraph graph = super.startGraph(dumpId, format, args);
                graphs.add(graph);
                return graph;
            }
        };

        try (InputStream raw = Files.newInputStream(input);
             DigestInputStream digesting = new DigestInputStream(raw, digest);
             BufferedInputStream in = new BufferedInputStream(digesting)) {
            new BinaryReader(new StreamSource(in), mb).parse();

            // StreamSource requires mark/reset. Buffering outside the digest
            // stream means replayed bytes come from the buffer and are not
            // hashed twice. Drain any parser-unconsumed tail so the digest
            // always covers the complete BGV file exactly once.
            byte[] drain = new byte[64 * 1024];
            while (in.read(drain) != -1) {
                // Drain only.
            }
        }
        return hex(digest.digest());
    }

    private static void countStack(Map<String, Long> counts, LocationStackFrame frame) {
        for (LocationStackFrame current = frame;
             current != null;
             current = current.getParent()) {
            countText(counts, current.getFullMethodName());
            for (LocationStratum stratum : current.getStrata()) {
                countText(counts, stratum.language);
                countText(counts, stratum.uri);
                countText(counts, stratum.file);
            }
        }
    }

    private static void countText(Map<String, Long> counts, String text) {
        if (text == null || text.isEmpty()) {
            return;
        }
        for (Map.Entry<String, Long> entry : counts.entrySet()) {
            String term = entry.getKey();
            if (term.isEmpty()) {
                continue;
            }
            long found = 0;
            int offset = 0;
            while (true) {
                int pos = text.indexOf(term, offset);
                if (pos < 0) {
                    break;
                }
                found++;
                offset = pos + term.length();
            }
            if (found != 0) {
                entry.setValue(entry.getValue() + found);
            }
        }
    }

    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            out.append(Character.forDigit((b >>> 4) & 0xf, 16));
            out.append(Character.forDigit(b & 0xf, 16));
        }
        return out.toString();
    }

    private static String quote(String value) {
        if (value == null) {
            return "null";
        }
        StringBuilder out = new StringBuilder(value.length() + 2);
        out.append('"');
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"': out.append("\\\""); break;
                case '\\': out.append("\\\\"); break;
                case '\b': out.append("\\b"); break;
                case '\f': out.append("\\f"); break;
                case '\n': out.append("\\n"); break;
                case '\r': out.append("\\r"); break;
                case '\t': out.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
            }
        }
        out.append('"');
        return out.toString();
    }
}
