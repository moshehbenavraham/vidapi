# HyperFrames Renderer

VidAPI includes a `hyperframes` renderer for HTML/CSS/GSAP-heavy compositions.
Clients still submit VidAPI composition JSON. VidAPI validates the public schema,
resolves assets through the normal asset service, compiles a workspace-local
HyperFrames project, and invokes the HyperFrames CLI behind the renderer
protocol.

## Selection

Use HyperFrames explicitly when a composition contains an HTML clip:

```json
{
  "renderer": "hyperframes",
  "timeline": {
    "tracks": [
      {
        "clips": [
          {
            "asset": {
              "type": "html",
              "html": "<div class=\"title\">Hello</div>",
              "css": ".title { font-size: 96px; }"
            },
            "length": 2
          }
        ]
      }
    ]
  }
}
```

When `renderer` is omitted, `null`, or `auto`, VidAPI selects HyperFrames only
if at least one HTML asset is present. Non-HTML compositions continue to select
Editly by default. Requests that force `editly` or `ffmpeg-native` for HTML
assets fail before queue admission with `UNSUPPORTED_RENDERER_FEATURE`.

## Runtime Dependencies

The worker runtime must provide:

- Node.js 22 or newer
- HyperFrames CLI (`hyperframes`)
- FFmpeg and ffprobe
- Chromium or the browser bundle used by HyperFrames
- The fonts expected by deployed compositions

The adapter calls HyperFrames in local CLI mode inside VidAPI's worker
container. It does not expose HyperFrames-native project schemas through the
VidAPI API.

## Security Boundaries

HTML assets are bounded and validated before browser work starts. VidAPI
rejects blank HTML, remote script tags, remote stylesheet links, CSS imports,
and direct remote media references that are not listed as explicit HTML media
references. Asset URLs are resolved by VidAPI's asset service before compile, so
the browser renderer consumes workspace-local file paths rather than fetching
media itself.

Inline script is intended for deterministic animation setup. It must not import
remote modules, load external code, or manually control media playback that the
HyperFrames runtime owns.

## Compile Artifacts

Each HyperFrames compile writes these workspace files:

- `index.html` - generated root composition and mapped clips
- `compiled.hyperframes.json` - deterministic VidAPI-to-HyperFrames render plan
- `replay.json` - redacted command, environment facts, inputs, and output path

The renderer produces an MP4 intermediate. Shared VidAPI finishing then handles
requested WebM, GIF, PNG sequence, poster generation, storage, logs, metrics,
and webhooks.

## Replay Metadata

Replay metadata is operational, not a raw request dump. It records the command,
arguments, timeout, workspace, input files, output path, Node/FFmpeg/browser
dependency hints, and requested output facts. It redacts callback URLs, query
strings, secret-looking values, raw HTML payloads, and full renderer specs.

## Failure Behavior

HyperFrames failures are mapped into bounded renderer errors:

- Missing CLI binary
- Node.js/runtime version failure
- Browser launch failure
- Timeout
- User cancellation
- Non-zero process exit
- Missing output file

The subprocess log is line-streamed and capped by `max_subprocess_stderr_bytes`.
Cancellation requests terminate the browser/Node subprocess with a grace period
and kill fallback.
