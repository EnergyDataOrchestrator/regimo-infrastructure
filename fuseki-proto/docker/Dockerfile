## Apache Jena Fuseki **Full** Dockerfile, adapted for the EDO/Regimo prototype.
##
## This builds the Fuseki *Full* distribution ("Fuseki Full with UI"): the
## `apache-jena-fuseki-<ver>.zip` webapp that serves the web UI at `/`, the
## admin endpoints (`/$/ping`, `/$/server`, `/$/datasets`, `/$/backup`, ...), and
## auto-scans `$FUSEKI_BASE/configuration/` for dataset assemblers.
##
## WHY NOT A REGISTRY IMAGE
## -------------------------
## Apache Jena does NOT publish a pre-built Fuseki image to any public registry
## (Docker Hub / GHCR). The "canonical" community image `stainless/jena-fuseki`
## that this prototype previously referenced no longer exists on Docker Hub
## (repo 404) — exactly why `fuseki-proto start` first failed with:
##   pull access denied for stainless/jena-fuseki ...
##
## The supported path is to BUILD from source: this image downloads the official
## Full release zip from Maven Central, verifies its SHA1, extracts it into
## `/fuseki` (which is also FUSEKI_BASE), and strips a minimal JRE via `jlink`.
##
## The previous iteration of this prototype ran the server-only Fuseki **main**
## (`jena-fuseki-server` jar), which has no web UI and no `/$/ping`. This file
## is the drop-in replacement that gives us the Full distribution instead —
## same pinned Jena version (5.1.0), same `FUSEKI_BASE=/fuseki` run area, so the
## compose service's volumes (`./config`, `./shapes`, `fuseki-data`) keep working.
##
## Usage from the compose file:
##   build: ./docker          # -> image built from this Dockerfile
##   (compose no longer passes --config; Full auto-scans FUSEKI_BASE/configuration)

ARG JAVA_VERSION=21
ARG ALPINE_VERSION=3.21.2
# The Apache Jena Fuseki (Full) release to install. Pinned for reproducibility.
# See https://repo1.maven.org/maven2/org/apache/jena/apache-jena-fuseki/
# Note: this is the **Full** distribution (web UI + admin endpoints), as opposed
# to the server-only `jena-fuseki-server` jar used by the earlier prototype.
ARG JENA_VERSION=5.1.0
ARG FUSEKI_DIR=/fuseki
ARG FUSEKI_ZIP=apache-jena-fuseki-${JENA_VERSION}.zip
ARG JAVA_MINIMAL=/opt/java-minimal

## ---- Stage: download the zip, compute the classpath modules, build a reduced JRE --
FROM eclipse-temurin:${JAVA_VERSION}-alpine AS base

ARG JAVA_MINIMAL
ARG JENA_VERSION
ARG FUSEKI_DIR
ARG FUSEKI_ZIP
ARG REPO=https://repo1.maven.org/maven2
ARG ZIP_URL=${REPO}/org/apache/jena/apache-jena-fuseki/${JENA_VERSION}/${FUSEKI_ZIP}

RUN [ "${JENA_VERSION}" != "" ] || { echo -e '\n**** Set JENA_VERSION ****\n' ; exit 1 ; }
RUN echo && echo "==== Docker build for Apache Jena Fuseki (Full) ${JENA_VERSION} ====" && echo

# Alpine: unzip for extraction, binutils for jlink's objcopy.
RUN apk add --no-cache curl unzip binutils

WORKDIR /tmp

# Download the release zip, verifying the SHA1 checksum from Maven Central.
COPY download.sh .
RUN chmod a+x download.sh
RUN ./download.sh --chksum sha1 "$ZIP_URL"

# Extract the Full distribution into FUSEKI_DIR (this dir doubles as FUSEKI_BASE).
RUN mkdir -p "${FUSEKI_DIR}" && \
    unzip -q "${FUSEKI_ZIP}" -d /tmp/fuseki-extract && \
    cp -a /tmp/fuseki-extract/apache-jena-fuseki-${JENA_VERSION}/. "${FUSEKI_DIR}/"

# Provide extra JDK modules that jdeps cannot detect by analysis. Notably:
#   * jdk.zipfs — the "jar" URI FileSystem provider Jetty needs to serve the
#     Fuseki webapp (jar:file:/fuseki/fuseki-server.jar!/); jdeps cannot see
#     this and without it the webapp fails to start with:
#       ProviderNotFoundException: Provider "jar" not found
#   * jdk.crypto.*, jdk.localedata, jdk.unsupported — Jena/Jetty runtime extras.
ARG JDEPS_EXTRA="jdk.zipfs,jdk.crypto.cryptoki,jdk.crypto.ec,jdk.localedata,jdk.unsupported"
# Optional: comma-separated locale language tags to keep (empty = all locales).
ARG JDK_LOCALES=""

# Decide which module list to feed jlink.
#
# NOTE: unlike a classic servlet container, the Full download does not ship a
# lib/*.jar webapp (no WEB-INF/lib) — all classes live in the single
# `fuseki-server.jar`. We therefore run jdeps over that one jar (exactly as the
# earlier server-only Dockerfile did). jdeps may still miss a module used only
# via reflection (e.g. xml crypto, mgmt) so the JDEPS_EXTRA set covers those.
RUN \
  JDEPS="$(jdeps --multi-release base --print-module-deps --ignore-missing-deps \
              ${FUSEKI_DIR}/fuseki-server.jar 2>/dev/null \
         | tr -d '\n')" && \
  if [ -z "${JDEPS}" ] ; then \
    echo "**** jdeps could not determine any modules — aborting build ****" ; exit 1 ; \
  fi && \
  echo "JDK modules for jlink: ${JDEPS},${JDEPS_EXTRA}" && \
  if [ -n "${JDK_LOCALES}" ] ; then LOCALE_OPT="--include-locales=${JDK_LOCALES}" ; else LOCALE_OPT="" ; fi && \
  jlink \
        --compress 2 --strip-debug --no-header-files --no-man-pages \
        --output "${JAVA_MINIMAL}" \
        --add-modules "${JDEPS},${JDEPS_EXTRA}" \
        ${LOCALE_OPT}

COPY entrypoint.sh /fuseki/entrypoint.sh
COPY log4j2.properties /fuseki/log4j2.properties

## ---- Stage: runtime (alpine + java-minimal + full fuseki distro) ----------
FROM alpine:${ALPINE_VERSION}

ARG JENA_VERSION
ARG JAVA_MINIMAL
ARG FUSEKI_DIR
ARG FUSEKI_ZIP

COPY --from=base /opt/java-minimal /opt/java-minimal
COPY --from=base /fuseki /fuseki

WORKDIR $FUSEKI_DIR

ARG LOGS=${FUSEKI_DIR}/logs
ARG DATA=${FUSEKI_DIR}/databases
ARG JENA_USER=fuseki
ARG JENA_GROUP=$JENA_USER
ARG JENA_GID=1000
ARG JENA_UID=1000

# Unprivileged user; -H : no home, -D : no password.
RUN addgroup -g "${JENA_GID}" "${JENA_GROUP}" && \
    adduser "${JENA_USER}" -G "${JENA_GROUP}" -s /bin/ash -u "${JENA_UID}" -H -D

# curl is used by the compose healthcheck (and by the README's in-container
# load examples). bash is required by the Fuseki-Full `fuseki-server` launcher.
RUN apk add --no-cache curl bash

RUN mkdir --parents "${FUSEKI_DIR}" && \
    chown -R $JENA_USER ${FUSEKI_DIR}

USER $JENA_USER

RUN \
    mkdir -p $LOGS && \
    mkdir -p $DATA && \
    chmod a+x entrypoint.sh fuseki-server fuseki

ENV \
    JAVA_HOME=${JAVA_MINIMAL}           \
    # JVM_ARGS is read by the distribution's `fuseki-server` launcher.
    JVM_ARGS="-Xmx4096m -Xms4096m"      \
    JENA_VERSION=${JENA_VERSION}        \
    FUSEKI_BASE="${FUSEKI_DIR}"        \
    FUSEKI_HOME="${FUSEKI_DIR}"

EXPOSE 3030

ENTRYPOINT ["./entrypoint.sh" ]
CMD []
