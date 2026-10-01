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

FROM ghcr.io/graalvm/graalvm-community:25i4-25.0.4.1.1-ol10@sha256:a7b4810d7c755e9627feaa1459eb5a93338643b16d745d4f3fc86db71e5da7f5

USER root

RUN microdnf install -y \
        findutils \
        diffutils \
        git \
        gzip \
        shadow-utils \
        tar \
        unzip \
        xz \
        procps \
        time \
        sudo \
    && microdnf clean all

RUN microdnf install -y \
        --enablerepo=ol10_codeready_builder \
        maven \
        maven-unbound \
    && microdnf clean all

ENV PATH="${JAVA_HOME}/bin:${PATH}"

ARG GH_VERSION=2.100.0
ARG GH_LINUX_AMD64_SHA256=e4d4bb4498e8d007abe545b6568926793ace1b6447da598294a610018cb164be

RUN curl --fail --location --silent --show-error \
        "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" \
        --output /tmp/gh.tar.gz \
    && echo "${GH_LINUX_AMD64_SHA256}  /tmp/gh.tar.gz" | sha256sum --check --strict - \
    && tar --extract --gzip \
        --file /tmp/gh.tar.gz \
        --directory /opt \
    && ln --symbolic "/opt/gh_${GH_VERSION}_linux_amd64/bin/gh" /usr/local/bin/gh \
    && gh --version \
    && rm /tmp/gh.tar.gz

RUN useradd --create-home --shell /bin/bash vscode \
    && echo "vscode ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/vscode \
    && chmod 0440 /etc/sudoers.d/vscode

USER vscode

RUN curl -fsSL https://claude.ai/install.sh | bash

WORKDIR /workspaces/protos-benchmarks

ENV MAVEN_OPTS="--enable-native-access=ALL-UNNAMED --sun-misc-unsafe-memory-access=allow"
