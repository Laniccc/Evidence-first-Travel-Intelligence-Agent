# Pinned Baidu MCP runtime

Install from this directory with `npm ci --ignore-scripts --no-audit --no-fund`.
The fixed local entrypoint is `node_modules/@baidumap/mcp-server-baidu-map/dist/index.js`;
use an administrator-configured Node executable, never query-supplied commands or request-time npx.

This package is not started by the current production factory. Online startup, credentials
and readiness are intentionally deferred to implementation Task 10.
BAIDU_MAP_API_KEY must come from deployment secrets and must not appear in logs.

The client allows only map_search_places and map_place_details. The server package exposes
more tools, but those are not available to this Agent. Source-code licensing does not
grant permission to retain provider data; this batch implements transient evidence only.

See docs/plans/2026-09-04-batch-b-verification.md at the repository root for the test and
capability boundaries. Ordinary tests start an offline Python fixture, not this Node server.
