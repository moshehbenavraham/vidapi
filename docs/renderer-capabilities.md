# Renderer Capabilities

VidAPI accepts renderer-neutral composition JSON and selects a concrete renderer
before compilation. The capability registry documents what each renderer can
handle and rejects unsupported combinations before a job enters expensive render
work.

## Selection Semantics

| Request renderer | Selected renderer | Behavior |
|------------------|-------------------|----------|
| omitted | `hyperframes` or `editly` | HyperFrames when an HTML asset is present; otherwise Editly. |
| `null` | `hyperframes` or `editly` | Treated the same as omitted. |
| `auto` | `hyperframes` or `editly` | HyperFrames when an HTML asset is present; otherwise Editly. |
| `editly` | `editly` | Explicit Editly rendering. |
| `ffmpeg-native` | `ffmpeg-native` | Explicit native FFmpeg rendering for the supported simple subset. |
| `hyperframes` | `hyperframes` | Explicit HTML/CSS/GSAP rendering; requires at least one HTML asset. |

Unknown renderer names are rejected by capability validation with a stable
VidAPI error envelope.

## Editly Support Matrix

| Feature | Supported values |
|---------|------------------|
| Asset types | `video`, `image`, `text`, `audio`, `color` |
| Output formats | `mp4`, `webm`, `gif`, `png-sequence` |
| Transitions | `fade_in`, `fade_out`, `crossfade`, `directional_left`, `directional_right`, `directional_up`, `directional_down`, `wipe_left`, `wipe_right`, `wipe_up`, `wipe_down`, `cross_zoom`, `simple_zoom`, `circle_open`, `linear_blur` |
| Captions | `sidecar`, `burn-in` |
| Caption sidecar formats | `srt`, `webvtt` |
| Poster controls | `default`, `timestamp`, `percent`, `disabled` |

Editly always renders an MP4 intermediate. WebM, GIF, and PNG sequence outputs
are supported through the shared FFmpeg output post-processing path.
Captions and request-level posters are implemented in the shared finishing path
around that intermediate, not by exposing Editly-native caption schemas.

## Native FFmpeg Support Matrix

| Feature | Supported values |
|---------|------------------|
| Asset types | `video`, `image`, `text`, `audio`, `color` |
| Output formats | `mp4`, `webm`, `gif`, `png-sequence` |
| Transitions | none |
| Captions | none |
| Poster controls | none |
| Fit modes | `cover`, `contain`, `stretch`, `none` |
| Audio | soundtrack and detached audio with trim, delay, volume, and `amix` |

The native renderer produces an MP4 intermediate and relies on the same shared
finishing path for WebM, GIF, PNG sequence, storage, logs, and default poster
generation. It consumes resolved local asset paths only. Unsupported native
features such as transitions, captions, poster controls, transforms, audio
effects, invalid colors, unresolved assets, and client-supplied filters are
rejected before FFmpeg work.

## HyperFrames Support Matrix

| Feature | Supported values |
|---------|------------------|
| Asset types | `html`, `image`, `video`, `audio`, `text`, `color` |
| Output formats | `mp4`, `webm`, `gif`, `png-sequence` |
| HTML fields | bounded inline `html`, optional `css`, optional deterministic inline `script`, explicit `media_refs` |
| Timing | absolute `start`, `length`, video/audio trim, volume, track z-order through HyperFrames `data-*` attributes |
| Runtime | Node.js 22+, HyperFrames CLI, FFmpeg, Chromium/browser dependencies |
| Captions | none at capability admission |
| Poster controls | none at capability admission |
| Transitions | none |
| Remote scripts/styles | rejected |

HyperFrames writes `index.html`, `compiled.hyperframes.json`, `replay.json`, and
workspace-local media copies before invoking the CLI. It produces an MP4
intermediate and relies on the shared finishing path for WebM, GIF, PNG
sequence, storage, logs, metrics, webhooks, and default poster generation.

The adapter does not fetch media from the browser. Media referenced by HTML
assets must be listed in `media_refs`, resolved by VidAPI's asset service, and
rewritten to local project paths during compile.

## Error Semantics

Renderer capability failures use the standard VidAPI managed error envelope:

```json
{
  "error": {
    "code": "UNSUPPORTED_RENDERER_FEATURE",
    "message": "Renderer does not support requested feature.",
    "context": {
      "renderer": "editly",
      "feature": "timeline.tracks[0].clips[0].transition.name",
      "requested": "wipe_left",
      "supported": ["fade_in"]
    }
  }
}
```

The context is intentionally bounded. It can include renderer names, feature
paths, and enum-like requested values, but it must not include raw composition
payloads, asset URLs, callback URLs, storage paths, renderer specs, stack
traces, or secrets.

Transition capability validation is intentionally separate from transition
semantic validation. A renderer can declare that it supports `wipe_left`, while
the shared transition validator still rejects a specific request if that
transition has no exact same-track successor, overlaps another clip, exceeds
incoming clip duration, or competes with another transition at the same rendered
boundary.

## Extension Points

Future adapters should add or update one capability record in
`app/renderers/capabilities.py`, then provide a concrete renderer behind the
existing renderer protocol. Route handlers and workers should continue to call
the shared selection and validation helpers rather than adding renderer-specific
branches.

Renderer adapters should map VidAPI transition enum values internally instead
of accepting renderer-native transition names or parameter objects from clients.
