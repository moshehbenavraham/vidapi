# Renderer Capabilities

VidAPI accepts renderer-neutral composition JSON and selects a concrete renderer
before compilation. The capability registry documents what each renderer can
handle and rejects unsupported combinations before a job enters expensive render
work.

## Selection Semantics

| Request renderer | Selected renderer | Behavior |
|------------------|-------------------|----------|
| omitted | `editly` | Default MVP renderer. |
| `null` | `editly` | Treated the same as omitted. |
| `auto` | `editly` | Selects the best available renderer; currently Editly. |
| `editly` | `editly` | Explicit Editly rendering. |
| `ffmpeg-native` | none | Reserved for a future adapter; currently rejected. |
| `hyperframes` | none | Reserved for a future adapter; currently rejected. |

Unknown renderer names are rejected by request schema validation. Known but
unavailable renderers are rejected by capability validation with a stable
VidAPI error envelope.

## Editly Support Matrix

| Feature | Supported values |
|---------|------------------|
| Asset types | `video`, `image`, `text`, `audio`, `color` |
| Output formats | `mp4`, `webm`, `gif`, `png-sequence` |
| Transitions | `fade_in`, `fade_out`, `crossfade` |
| Captions | `sidecar`, `burn-in` |
| Caption sidecar formats | `srt`, `webvtt` |
| Poster controls | `default`, `timestamp`, `percent`, `disabled` |

Editly always renders an MP4 intermediate. WebM, GIF, and PNG sequence outputs
are supported through the shared FFmpeg output post-processing path.
Captions and request-level posters are implemented in the shared finishing path
around that intermediate, not by exposing Editly-native caption schemas.

## Error Semantics

Renderer capability failures use the standard VidAPI managed error envelope:

```json
{
  "error": {
    "code": "UNSUPPORTED_RENDERER_FEATURE",
    "message": "Renderer does not support requested feature.",
    "context": {
      "renderer": "editly",
      "renderer": "hyperframes",
      "reason": "unavailable",
      "available_renderers": ["editly"]
    }
  }
}
```

The context is intentionally bounded. It can include renderer names, feature
paths, and enum-like requested values, but it must not include raw composition
payloads, asset URLs, callback URLs, storage paths, renderer specs, stack
traces, or secrets.

## Extension Points

Future adapters should add or update one capability record in
`app/renderers/capabilities.py`, then provide a concrete renderer behind the
existing renderer protocol. Route handlers and workers should continue to call
the shared selection and validation helpers rather than adding renderer-specific
branches.
