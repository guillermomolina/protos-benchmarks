# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.
#
# Official GraalVM Community 25.3.4.1, independently pinned from the 25.4
# Protos/JS/Python runner. The Ruby Maven embedding distribution is baked
# into this image during the explicit Podman build (never during measurement).
FROM ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10@sha256:636592a38dbd6461e71aaf019ed1ff1f389c171540bc2cb632fd73e6ec7848d7

USER root

RUN microdnf install -y \
    findutils diffutils git gzip shadow-utils tar unzip xz procps time \
    python3 util-linux-core && \
    microdnf install -y --enablerepo=ol10_codeready_builder \
    maven maven-unbound && \
    microdnf clean all

ENV PATH="${JAVA_HOME}/bin:${PATH}"
ENV MAVEN_OPTS="--enable-native-access=ALL-UNNAMED --sun-misc-unsafe-memory-access=allow"

# Fixed, published Maven distribution for the JVM embedding API: the Ruby
# runtime AND its standard-library resources are cached in a dedicated image
# path, unaffected by the host's mounted .m2 cache for the other languages.
COPY policy/ruby-peer.pom.xml /opt/protos-ruby-runtime/pom.xml
RUN mkdir -p /opt/protos-ruby-runtime/m2 && \
    mvn -q -U \
      -Dmaven.repo.local=/opt/protos-ruby-runtime/m2 \
      -f /opt/protos-ruby-runtime/pom.xml \
      dependency:build-classpath \
      -Dmdep.outputFile=/opt/protos-ruby-runtime/classpath.txt

RUN java -version 2>&1 | grep -F 'GraalVM CE 25.3.4.1' && \
    mvn -version | grep -F 'Apache Maven' && \
    command -v taskset && \
    test -s /opt/protos-ruby-runtime/classpath.txt && \
    grep -F '/dev/truffleruby/internal/runtime/40.0.0/' \
      /opt/protos-ruby-runtime/classpath.txt && \
    grep -F '/dev/truffleruby/internal/resources/40.0.0/' \
      /opt/protos-ruby-runtime/classpath.txt && \
    grep -F '/org/graalvm/truffle/truffle-api/25.3.4.1/' \
      /opt/protos-ruby-runtime/classpath.txt

ENV PROTOS_RUBY_IMAGE_CLASSPATH=/opt/protos-ruby-runtime/classpath.txt

RUN useradd --create-home --shell /bin/bash vscode
USER vscode
WORKDIR /workspaces/protos-benchmarks
