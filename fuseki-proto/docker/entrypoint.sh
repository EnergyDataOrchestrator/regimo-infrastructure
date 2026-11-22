#!/bin/sh
## Licensed under the terms of http://www.apache.org/licenses/LICENSE-2.0

## Apache Jena Fuseki *Full* entrypoint.
##
## We use the distribution's own `fuseki-server` launcher (the supported way to
## run Fuseki Full), which builds the correct classpath and starts
## org.apache.jena.fuseki.cmd.FusekiCmd. Because we unpack the distribution into
## /fuseki and set FUSEKI_HOME=/fuseki (ENV), the launcher finds
## /fuseki/fuseki-server.jar and serves the web UI from /fuseki/webapp.
##
## FUSEKI_BASE=/fuseki is set (ENV) so the server:
##   * serves the web UI at /
##   * exposes the admin endpoints: /$/ping, /$/server, /$/datasets, /$/backup
##   * auto-scans $FUSEKI_BASE/configuration/ for dataset assemblers (*.ttl)
##
## JVM_ARGS controls the JVM heap (set in the image ENV).
## Additional CLI args are passed through to Fuseki.

exec /fuseki/fuseki-server "$@"
