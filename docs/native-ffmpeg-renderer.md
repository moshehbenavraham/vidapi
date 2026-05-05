# Native FFmpeg Renderer

VidAPI includes an explicit `ffmpeg-native` renderer for simple, deterministic
timelines. It is selected only when a request sets:

```json
{
  "renderer": "ffmpeg-native"
}
```

`auto` continues to select Editly. `hyperframes` remains unavailable. The native
renderer is intentionally narrow: it compiles a supported subset of the public
VidAPI composition schema into a bounded FFmpeg command and writes replay
artifacts for debugging.

## Support Matrix

| Feature | Native support |
|---------|----------------|
| Assets | `color`, `image`, `video`, `text`, `audio` |
| Output intermediate | MP4 |
| Requested outputs | `mp4`, `webm`, `gif`, `png-sequence` through shared finishing |
| Fit modes | `cover`, `contain`, `stretch`, `none` |
| Position | Named positions and normalized coordinates with offsets |
| Opacity | Supported for visual clips |
| Timing | Absolute `start`, `length`, video trim, audio trim, audio delay |
| Audio | Video audio, soundtrack, detached audio clips, volume, `amix` |
| Captions | Not supported by native capability admission |
| Poster options | Not supported by native capability admission |
| Transitions | Not supported |
| Transforms | Not supported |

Text clips are rendered to PNG by the existing text asset resolver before the
native renderer compiles. The native renderer consumes only local resolved asset
paths and never fetches remote URLs during compile or render.

## Request Example

```json
{
  "renderer": "ffmpeg-native",
  "timeline": {
    "background": "#111111",
    "tracks": [
      {
        "clips": [
          {
            "asset": {"type": "color", "color": "#111111"},
            "length": 2
          },
          {
            "asset": {"type": "image", "src": "https://example.com/title.png"},
            "start": 0.25,
            "length": 1.5,
            "fit": "contain",
            "position": "center"
          }
        ]
      }
    ]
  },
  "output": {
    "format": "mp4",
    "width": 1280,
    "height": 720,
    "fps": 30
  }
}
```

## Rejection Behavior

Unsupported native combinations fail before expensive render work whenever they
are visible to the capability registry. Compile-time native subset validation
then rejects renderer-specific unsupported shapes such as transforms, unresolved
assets, invalid overlay geometry, unsupported timeline features, and unsafe
asset usage.

Errors use bounded context. They may include renderer names, field paths,
requested enum values, and supported values. They must not include raw request
payloads, callback URLs, asset URLs with query strings, stack traces, or
secrets.

Example unsupported-feature context:

```json
{
  "renderer": "ffmpeg-native",
  "feature": "timeline.tracks[0].clips[0].transition.name",
  "requested": "wipe_left",
  "supported": []
}
```

## Replay Artifacts

Native compile writes:

- `compiled.ffmpeg.json` - deterministic command, filter graph, input mapping,
  output path, and plan metadata.
- `replay.json` - safe command and environment facts for rerunning the render
  locally.
- `render.log` - bounded FFmpeg stderr captured during execution.

Shared output finishing may add WebM, GIF, PNG sequence, manifest, poster, and
caption artifacts after the native MP4 intermediate is produced.
