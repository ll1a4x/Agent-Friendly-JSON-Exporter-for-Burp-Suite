# Agent-Friendly JSON Exporter for Burp Suite

A Burp Suite extension that exports Proxy history to structured JSON optimized for consumption by LLM-powered coding agents (Claude Code, opencode, Codex CLI, etc.) during vulnerability analysis.

## Why This Exists

Burp's native XML export and simple JSON dumps force agents to do unnecessary parsing work — headers come as flat arrays, bodies arrive base64-encoded or mixed with binary data, and there's no way to reference specific items by ID. This extension produces JSON that agents can consume directly, with headers as dicts, query parameters pre-extracted, body types classified, and binary/oversized content safely truncated.

It generates two complementary artifacts:

- **`proxy_index.jsonl`** — a lightweight one-line-per-request summary for cheap scanning and grep
- **`proxy_full.json`** — complete structured data with parsed headers, classified bodies, and enrichment

The two-file design mirrors how coding agents analyze large codebases: survey the index first, drill into specific items as needed. This keeps context windows focused and token usage efficient on large engagements.

## Requirements

- Burp Suite Professional or Community (tested on 2024.x and later)
- Jython 2.7.3+ standalone JAR configured in Burp
- Write access to the output directory

If you haven't set up Jython in Burp yet, download `jython-standalone-2.7.3.jar` (or newer) from the official Jython site and point Burp to it via **Settings → Extensions → Python environment**.

## Installation

Clone or download this repository, then load the extension into Burp:

1. Open Burp Suite and navigate to **Extensions → Installed → Add**
2. Set **Extension type** to `Python`
3. Select `json_exporter.py` from this repository
4. Click **Next** — the extension loads silently and registers a context menu item

No configuration file is needed. The extension stores no state and can be safely unloaded or reloaded at any time.

## Usage

### Basic Export

1. In Burp, go to **Proxy → HTTP history**
2. Select the requests you want to export (press `Cmd+A` / `Ctrl+A` to select all)
3. Right-click the selection → **Extensions → Agent-Friendly JSON Exporter**
4. Choose one of three export modes:
   - **Export as JSON (full)** — writes `proxy_full.json` only
   - **Export as JSONL (index)** — writes `proxy_index.jsonl` only
   - **Export both (index + full)** — writes both files in the same directory
5. A directory picker appears — choose where to save the files

Progress and completion messages print to the extension's output console (**Extensions → Installed → select the extension → Output**).

### Recommended Workflow for Agent Analysis

For most vulnerability-analysis workflows, pick **Export both** and point your agent at the output directory. A typical agent prompt looks like:

```
Analyze the Burp proxy history in this directory. Start by reading
proxy_index.jsonl to identify interesting endpoints — focus on:
- Authentication and session-handling requests
- API endpoints with user-controlled parameters
- File upload and download handlers
- Admin or privileged functionality

Then load the corresponding full items from proxy_full.json and analyze
them for OWASP Top 10 vulnerabilities. Report findings with severity,
affected request IDs, and suggested exploitation paths.
```

The agent surveys ~200 bytes per item in the index, then selectively loads full requests only where needed. On a 500-item proxy history, this typically reduces token usage by 80–90% compared to loading everything.

## Output Format

### `proxy_index.jsonl`

One JSON object per line. Designed for fast scanning and tools like `jq`, `grep`, and `rg`:

```json
{"id":1,"method":"GET","url":"https://app.example.com/api/users/42","status":200,"len":128,"ctype":"json"}
{"id":2,"method":"POST","url":"https://app.example.com/api/login","status":200,"len":256,"ctype":"json"}
{"id":3,"method":"GET","url":"https://app.example.com/static/bundle.js","status":200,"len":1847293,"ctype":"javascript"}
```

Fields: `id`, `method`, `url`, `status`, `len` (response body length in bytes), `ctype` (classified body type).

### `proxy_full.json`

A single JSON object with a metadata wrapper and an array of fully-structured items:

```json
{
  "metadata": {
    "export_time": "2026-04-23T14:30:00Z",
    "total_items": 247
  },
  "items": [
    {
      "id": 1,
      "timestamp": "2026-04-23T14:30:00Z",
      "url": "https://app.example.com/api/users/42?filter=active",
      "host": "app.example.com",
      "port": 443,
      "protocol": "https",
      "method": "GET",
      "path": "/api/users/42",
      "query_params": {"filter": "active"},
      "request": {
        "headers": {
          "Host": "app.example.com",
          "Authorization": "Bearer eyJhbGciOi...",
          "User-Agent": "Mozilla/5.0 ...",
          "Cookie": "session=abc123"
        },
        "body": null,
        "body_type": null,
        "body_length": 0
      },
      "response": {
        "status": 200,
        "headers": {
          "Content-Type": "application/json",
          "X-Powered-By": "Express"
        },
        "body": "{\"id\":42,\"email\":\"user@example.com\",\"role\":\"admin\"}",
        "body_type": "json",
        "body_length": 52,
        "mime_type": "JSON"
      }
    }
  ]
}
```

### Body Type Classifications

The `body_type` field normalizes Content-Type into a small set of categories for easier agent reasoning:

| Value | Matches |
|-------|---------|
| `json` | `application/json`, `application/*+json` |
| `xml` | `application/xml`, `text/xml`, `*+xml` |
| `form` | `application/x-www-form-urlencoded` |
| `multipart` | `multipart/form-data` |
| `html` | `text/html` |
| `javascript` | `application/javascript`, `text/javascript` |
| `binary` | `image/*`, `video/*`, `audio/*`, `application/octet-stream` |
| `text` | any other text-like content |
| `null` | no Content-Type header (typical for GET requests with no body) |

## Content Handling

**Binary responses** (images, videos, octet-stream) have their body replaced with a placeholder like `<binary content omitted, length=45231>`. Headers and metadata are preserved so agents can still reason about the response without wasting tokens on undecodable bytes.

**Oversized bodies** (default limit: 50,000 characters) are truncated with a marker indicating how many bytes were cut. This keeps minified JS bundles and large JSON blobs from blowing out agent context windows. Adjust `max_len` in `build_entry()` if you need different behavior.

**URL encoding and base64** in bodies is preserved as-is — the extension does not auto-decode. If you need decoded versions, add a post-processing step or let the agent decode inline during analysis.

## Tips for Effective Agent Analysis

**Scope your export.** Select only in-scope requests before exporting. A focused 100-item export analyzes faster and more accurately than an unfiltered 2000-item dump that includes third-party tracking, CDN assets, and OCSP requests.

**Filter static assets.** Before exporting, use Burp's Proxy history filter to hide responses with body types like `image/*`, `font/*`, and `text/css`. These rarely contribute to vulnerability analysis and add noise.

**Combine with repeater exports.** For deep-dive analysis of specific endpoints, export the Proxy history alongside your Repeater tabs for those endpoints. Agents can correlate passive observation (Proxy) with manual testing (Repeater).

**Redact before sharing.** If you're sharing exports with cloud-based agents, the files will contain authentication tokens, session cookies, and potentially PII. Consider running a redaction pass or using a local-only agent setup when handling sensitive engagement data.

## Known Limitations

The extension currently does not:

- Decode Burp's comment/highlight metadata (planned)
- Cluster similar requests (e.g., grouping `/api/users/{id}` variations)
- Include WebSocket messages — only HTTP/HTTPS traffic is exported
- Support streaming export for very large histories (all data is held in memory during export)

For histories larger than ~10,000 items, consider exporting in batches by date range using Burp's Proxy filter.

## Troubleshooting

**"Extension failed to load"** — verify your Jython standalone JAR is 2.7.3 or newer and correctly configured in Burp's Python environment settings.

**Right-click menu doesn't appear** — make sure the extension is enabled in **Extensions → Installed** and that you're right-clicking on selected Proxy history rows (not empty space).

**Large exports hang Burp** — Jython is single-threaded and holds all items in memory during export. For histories over 5000 items, export in smaller batches or increase Burp's JVM heap size via the `-Xmx` flag.

**Bodies appear garbled** — Burp stores binary responses as raw bytes, and Jython's string conversion may produce mojibake for non-UTF-8 content. These responses should be classified as `binary` and have their bodies omitted; if you see garbled text in supposedly-text responses, the server is likely mis-declaring its Content-Type.

## License

This project is licensed under the Apache License 2.0. See LICENSE for details.
