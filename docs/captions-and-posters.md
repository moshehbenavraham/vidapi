# Captions and Posters

VidAPI supports request-level caption and poster finishing options on the
composition schema. Captions are client-supplied timed cues. VidAPI does not
generate speech-to-text captions.

## Captions

Captions are supplied as a top-level `captions` block:

```json
{
  "captions": {
    "mode": "sidecar",
    "format": "srt",
    "cues": [
      {
        "start": 0.0,
        "end": 1.5,
        "text": "First line"
      }
    ]
  }
}
```

Supported modes:

| Mode | Behavior |
|------|----------|
| `sidecar` | Store a caption file next to the render output. |
| `burn-in` | Burn captions into the rendered video before output conversion. |

Supported sidecar formats:

| Format | Media Type |
|--------|------------|
| `srt` | `application/x-subrip` |
| `webvtt` | `text/vtt; charset=utf-8` |

Burn-in uses generated ASS captions internally. Clients do not supply ASS files
or FFmpeg filter text.

## Posters

Poster generation is configured under `output.poster`:

```json
{
  "output": {
    "format": "mp4",
    "poster": {
      "mode": "timestamp",
      "timestamp": 1.25
    }
  }
}
```

Supported modes:

| Mode | Behavior |
|------|----------|
| `default` | Use the configured service default timestamp. |
| `timestamp` | Extract the poster at a specific timestamp in seconds. |
| `percent` | Extract the poster at a percentage of render duration. |
| `disabled` | Do not generate a poster when the output format allows it. |

Omitting `output.poster` preserves the historical default poster behavior.

## Artifacts

Successful render status responses and webhook payloads can include:

| Field | Description |
|-------|-------------|
| `poster` | Backward-compatible poster URL string. |
| `poster_metadata` | Structured poster mode, timestamp, media type, and URL. |
| `captions` | Structured caption sidecar or burn-in metadata. |

All client-facing URLs are resolved through the storage URL resolver. The
database stores durable artifact URIs and safe metadata, not presigned URLs,
local implementation details, callback URLs, or raw composition JSON.
