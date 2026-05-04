There is currently no open‑source repo that is a full, drop‑in clone of Creatomate or JSON2Video, but a handful of GitHub projects come quite close in spirit — the strongest being HeyGen’s HyperFrames, the Shottower Shotstack backend clone, Mic’s story‑json‑to‑video, and a few JSON‑driven API/CLI tools. [github](https://github.com/DblK/shottower)

Below is a ranked map of the closest OSS options and how they relate to Creatomate/JSON2Video.

***

## What Creatomate & JSON2Video Actually Provide

- **Creatomate** is a commercial video/image generation API built around templates and “JSON‑to‑video”: you describe scenes, text, images, audio, animations, and timing in JSON and POST it to their REST API, which renders an MP4/GIF and returns a render status plus URL. [creatomate](https://creatomate.com/blog/json-to-video-practical-examples)
- **JSON2Video** is a very similar “video editing API” that uses JSON templates with variables; you define templates (with placeholders), send variable data via API, and the service handles editing, encoding, and rendering at scale (ads, social clips, product videos, etc.). [json2video](https://json2video.com)

Both expose REST APIs, use JSON to describe timelines/scenes, support dynamic data via variables, and hide an FFmpeg‑like backend. [rendi](https://www.rendi.dev/blog/best-video-generation-apis)

When looking for OSS “clones”, the closest matches are:  
1) services that accept JSON/markup and output video via FFmpeg, and  
2) frameworks that let you define a full video declaratively and render it programmatically.

***

## Tier 1 – Closest API‑Style Clones

### 1. Shottower (Shotstack backend clone)

**Repo:** https://github.com/DblK/shottower [github](https://github.com/DblK/shottower)

- Shottower is “an open source, self‑hosted implementation of the Shotstack backend server,” i.e., it re‑implements Shotstack’s commercial JSON‑to‑video API backend in Go. [github](https://github.com/DblK/shottower)
- Shotstack itself is a cloud “video editing API” that lets you post a JSON timeline (tracks, clips, assets, output options) and renders video using FFmpeg; Shottower uses the same concepts and API terms and translates that JSON into FFmpeg commands. [github](https://github.com/shotstack)

**Why it’s close to Creatomate/JSON2Video**

- It exposes a REST API with endpoints to create renders, check status, and download outputs, mirroring the SaaS pattern. [github](https://github.com/DblK/shottower)
- The JSON model has `Timeline`, `Track`, `Clip`, and various `Asset` types (VideoAsset, ImageAsset, AudioAsset, etc.), very similar to how Creatomate/JSON2Video represent compositions. [shotstack](https://shotstack.io/use-cases/scenarios/api/json-to-video-api/)
- It already supports much of Shotstack’s schema (tracks, start/length, scale, position, resolution, fps, quality, callbacks), i.e., a full timeline‑based engine you can call programmatically. [github](https://github.com/DblK/shottower)

**Limitations vs Creatomate/JSON2Video**

- Template management endpoints (`Create Template`, `Render Template`, etc.) are not yet implemented, so you don’t get a first‑class “template library” like Creatomate/JSON2Video out of the box. [github](https://github.com/DblK/shottower)
- Some features (HTMLAsset, TitleAsset, advanced audio controls, transitions, effects) are not fully implemented, and the author explicitly says it’s not built for heavy transcoding workloads. [github](https://github.com/DblK/shottower)

**Takeaway:** If you want a self‑hosted JSON‑driven video editing API that is the closest structurally to JSON2Video/Creatomate, Shottower is the strongest match today. [github](https://github.com/shotstack)

***

### 2. HyperFrames (HTML‑to‑MP4, agent‑native)

**Repo:** https://github.com/heygen-com/hyperframes [reddit](https://www.reddit.com/r/heygen/comments/1snl38i/hyperframes_opensource_framework_that_turns_html/)

- HyperFrames is an open‑source framework from HeyGen that converts HTML into MP4 video; authoring is standard HTML with a few data attributes, and the renderer produces consistent MP4 outputs. [reddit](https://www.reddit.com/r/ClaudeAI/comments/1snkiti/hyperframes_oss_framework_for_ai_agents_to_author/)
- It is explicitly positioned as an “agent‑native” / AI‑automation‑friendly HTML‑to‑video toolchain, with Apache 2.0 licensing and a requirement for Node 22+ and FFmpeg. [notes.nicolasdeville](https://notes.nicolasdeville.com/github/hyperframes-video/)

**Why it’s close to Creatomate**

- Creatomate heavily markets “JSON‑to‑video” and web‑style layout (CSS, animations) for programmatic video composition; HyperFrames does the same thing but with HTML/CSS/JS as the primary authoring format. [creatomate](https://creatomate.com/blog/json-to-video-how-to-create-videos-from-json)
- You can treat each HTML composition as a “template” and drive it from external data or AI agents, very similar to using Creatomate templates plus variables. [reddit](https://www.reddit.com/r/heygen/comments/1snl38i/hyperframes_opensource_framework_that_turns_html/)

**Differences**

- HyperFrames itself is a rendering framework, not a hosted multi‑tenant SaaS; you’d wrap it with your own API for multi‑user, job queueing, webhooks, etc. [reddit](https://www.reddit.com/r/ClaudeAI/comments/1snkiti/hyperframes_oss_framework_for_ai_agents_to_author/)
- Authoring is HTML rather than a bespoke JSON schema; you’d implement your own mapping from JSON to HTML if you want JSON2Video‑style behavior. [reddit](https://www.reddit.com/r/heygen/comments/1snl38i/hyperframes_opensource_framework_that_turns_html/)

**Takeaway:** HyperFrames is arguably the closest open‑source analogue to “Creatomate’s HTML/JSON‑to‑video engine” if you’re comfortable building your own API layer and template orchestration around it. [notes.nicolasdeville](https://notes.nicolasdeville.com/github/hyperframes-video/)

***

### 3. Video Artist API (video-artist-api)

**Repo:** https://github.com/ashishsaini/video-artist-api [github](https://github.com/ashishsaini/video-artist-api)

- “Video Artist” is a “smart and simple API for generating automated videos” that lets you create videos from a simple JSON structure describing slides and overlays. [github](https://github.com/ashishsaini/video-artist-api/blob/main/main_v2.py)
- The repo includes Docker support and exposes an HTTP API (e.g., a `/preview` endpoint) where you POST JSON like `{"slides":[{"overlay":[{"type":"text","value":"Welcome"}]}]}` and it auto‑selects relevant background images/videos via Pexels. [github](https://github.com/ashishsaini/video-artist-api)

**Why it’s similar**

- It’s explicitly an “API platform” for automated video generation, not just a library; you talk to it over HTTP like you would with Creatomate/JSON2Video. [github](https://github.com/ashishsaini/video-artist-api)
- The composition is defined via JSON (slides, overlay elements), making it conceptually close to JSON2Video’s JSON templates, just with a more limited schema. [github](https://github.com/topics/automated-videos)
- It integrates optional TTS (Microsoft Azure) and stock media selection (Pexels), so you can assemble news/product/how‑to videos programmatically. [github](https://github.com/ashishsaini/video-artist-api)

**Limitations**

- The JSON schema is much simpler than Creatomate/JSON2Video: slides + overlays rather than a full multi‑track timeline with arbitrary assets, transitions, and complex animations. [github](https://github.com/ashishsaini/video-artist-api)
- The author notes it’s “not a production ready project”, so you’d likely need to harden it for serious workloads. [github](https://github.com/ashishsaini/video-artist-api)

**Takeaway:** If you want an OSS API server that feels most like “a smaller JSON2Video”, Video Artist is a strong candidate, though it’s more opinionated and less feature‑rich than the commercial services. [github](https://github.com/topics/automated-videos)

***

## Tier 2 – JSON‑to‑Video Tools (CLI / Library)

### 4. Mic’s story-json-to-video

**Repo:** https://github.com/micnews/story-json-to-video [github](https://github.com/micnews/story-json-to-video)

- This tool compiles `story.json` documents into a video file (`story.mp4`) via a simple CLI command `story-json-to-video story.json`. [github](https://github.com/heygen-com/hyperframes)
- It uses FFmpeg and node‑canvas under the hood, and requires a set of native dependencies (Cairo, Pango, libpng, etc.) to render frames. [github](https://github.com/micnews/story-json-to-video)

**Why it’s similar**

- The story JSON format is a declarative description of a “story” layout (text, images, etc.), and the tool renders that JSON description into a video, i.e., literal JSON‑to‑video. [github](https://github.com/ampproject/amp-wp/issues/968)
- Functionally, it demonstrates the same idea as JSON2Video/Creatomate: a structured document → ffmpeg‑composited video pipeline. [creatomate](https://creatomate.com/blog/json-to-video-practical-examples)

**Differences**

- It’s a CLI/library, not a multi‑tenant API service with templates, variables, and render queues; you’d need to wrap it in your own HTTP service. [github](https://github.com/micnews/story-json-to-video)
- The supported feature set is narrower (aimed at “story” layouts); the README notes that not all `story-json` features are implemented. [github](https://github.com/micnews/story-json-to-video)

***

### 5. CJV-Command-Line (CJV – “Convert JSON to Video”)

**Repo:** https://github.com/ChuckGarcian/CJV-Command-Line [github](https://github.com/ChuckGarcian/CJV-Command-Line)

- CJV is described as “CJV (JSON‑to‑Video): A command‑line tool that processes JSON files adhering to a specific format to generate folder with videos.” [github](https://github.com/ChuckGarcian/CJV-Command-Line)
- It’s implemented primarily in C, with a small amount of shell glue. [github](https://github.com/ChuckGarcian/CJV-Command-Line)

**Why it’s relevant**

- Like story‑json‑to‑video, it takes JSON that follows a defined schema and emits videos, directly mirroring the JSON‑to‑video concept. [creatomate](https://creatomate.com/blog/json-to-video-practical-examples)
- Being C‑based, it’s a low‑level example of how one might parse JSON and drive FFmpeg or similar tools to generate videos.  

**Limitations**

- There’s no public documentation in the snippet about the exact JSON schema or features; the project has no stars and appears experimental. [github](https://github.com/ChuckGarcian/CJV-Command-Line)
- It’s CLI‑only; adding a Creatomate‑style API would be a significant additional build.  

***

### 6. AI-Video-Gen-by-ARABIAN-AI-SCHOOL

**Repo:** https://github.com/Arabianaischool/AI-Video-Gen-by-ARABIAN-AI-SCHOOL [github](https://github.com/Arabianaischool/AI-Video-Gen-by-ARABIAN-AI-SCHOOL)

- This pipeline generates short videos from a script: it splits text into lines, calls an AI image API (Pollinations) for visuals, assembles images/video, audio, and captions using MoviePy, FFmpeg, and ImageMagick, and streams progress via SSE. [github](https://github.com/Arabianaischool/AI-Video-Gen-by-ARABIAN-AI-SCHOOL)

**Why it’s related**

- It programmatically assembles videos from structured text and asset generation, similar in concept to JSON2Video workflows (script/metadata → composed video). [json2video](https://json2video.com)
- The code shows how to orchestrate AI asset generation + traditional compositing to automate creation of YouTube Shorts / social clips. [github](https://github.com/Arabianaischool/AI-Video-Gen-by-ARABIAN-AI-SCHOOL)

**Differences**

- There’s no generic JSON timeline/template schema; it’s a specific “script → short video” pipeline, not a general editing API. [github](https://github.com/Arabianaischool/AI-Video-Gen-by-ARABIAN-AI-SCHOOL)
- Again, CLI/server script, not a templated REST platform.  

***

## Tier 3 – Frameworks You Can Wrap Into a Clone

### 7. Remotion (React‑based programmable video)

**Repo:** https://github.com/remotion-dev/remotion [github](https://github.com/remotion-dev/remotion)

- Remotion is a framework for “creating videos programmatically using React”; each frame is rendered with React components, leveraging HTML/CSS/Canvas/SVG and then rendered to video. [dev](https://dev.to/mayu2008/new-clauderemotion-to-create-amazing-videos-using-ai-37bp)

**How it maps to Creatomate/JSON2Video**

- It gives you a full code‑driven composition system (dynamic text, data binding, animations, etc.), much like Creatomate/JSON2Video templates, but authoring is React code instead of JSON. [dev](https://dev.to/mayu2008/new-clauderemotion-to-create-amazing-videos-using-ai-37bp)
- The official ecosystem supports server‑side rendering to MP4 and you can build API layers that accept JSON and translate to props for React components.  

**Why it’s not a “clone”**

- Out of the box, it’s a library/framework, not an HTTP API with template/version management, webhooks, etc. [github](https://github.com/remotion-dev/remotion)
- You’d be building a fair bit of infra to get to “Creatomate‑as‑a‑service” using Remotion as the render engine.  

***

### 8. OpenShot Cloud API + SDKs (commercial API on OSS core)

**Core editor repo:** https://github.com/OpenShot/openshot-qt (GUI) – not itself an API, but the base editor.  
**Go SDK:** https://github.com/Bimde/openshot-sdk-go [github](https://github.com/Bimde/openshot-sdk-go)

- OpenShot Cloud API is a paid SaaS that exposes a RESTful video editing API built on the open‑source OpenShot editor; their docs show how to create projects, upload media, add clips, apply preset animations, and export via HTTP. [openshot](https://www.openshot.org/cloud-api/)
- The Go SDK illustrates how to programmatically create projects, files, clips, and exports against that API. [github](https://github.com/Bimde/openshot-sdk-go)

**Relevance and caveats**

- Architecturally, it’s very similar to JSON2Video/Creatomate: multi‑track timeline, clips, transitions, exports driven over HTTP. [openshot](https://www.openshot.org/cloud-api/)
- However, the actual cloud API backend is **not** open‑source; only the desktop editor and client SDKs are OSS, so it doesn’t meet your “open‑source GitHub clone of the service” requirement strictly. [reddit](https://www.reddit.com/r/OpenShot/comments/j6hz39/openshot_cloud_api_compile/)

***

## Quick Ranking Table (How Close Is Each?)

| Project | Host / Type | Authoring format | Self‑hostable? | How close to Creatomate/JSON2Video? |
| --- | --- | --- | --- | --- |
| **Shottower** (Shotstack backend clone)  [github](https://github.com/DblK/shottower) | Go backend, REST API, FFmpeg | Shotstack JSON timeline (tracks, clips, assets)  [github](https://github.com/DblK/shottower) | Yes (Go binary / Docker)  [github](https://github.com/DblK/shottower) | Closest structural match: real JSON‑to‑video API backend; templating and some features still incomplete. |
| **HyperFrames** (HeyGen)  [reddit](https://www.reddit.com/r/heygen/comments/1snl38i/hyperframes_opensource_framework_that_turns_html/) | Node + FFmpeg framework | HTML/CSS/JS with data attributes  [reddit](https://www.reddit.com/r/heygen/comments/1snl38i/hyperframes_opensource_framework_that_turns_html/) | Yes (Node 22+; Apache 2.0)  [reddit](https://www.reddit.com/r/heygen/comments/1snl38i/hyperframes_opensource_framework_that_turns_html/) | Very close in spirit to Creatomate’s web‑style composition; you must build your own API/templates/variable layer. |
| **Video Artist API**  [github](https://github.com/ashishsaini/video-artist-api) | Python/JS stack, REST API | Simple JSON (`slides`, `overlay` elements)  [github](https://github.com/ashishsaini/video-artist-api) | Yes (Dockerized)  [github](https://github.com/ashishsaini/video-artist-api) | “Mini JSON2Video” – ready‑made API but much narrower schema and not production‑hardened. |
| **story-json-to-video**  [github](https://github.com/micnews/story-json-to-video) | Node CLI using FFmpeg + node‑canvas | `story.json` (story layout JSON)  [github](https://github.com/micnews/story-json-to-video) | Yes (CLI/lib)  [github](https://github.com/micnews/story-json-to-video) | Good JSON‑to‑video example; no SaaS/API features, story‑specific schema. |
| **CJV‑Command‑Line**  [github](https://github.com/ChuckGarcian/CJV-Command-Line) | C CLI tool | Custom JSON schema  [github](https://github.com/ChuckGarcian/CJV-Command-Line) | Yes (CLI)  [github](https://github.com/ChuckGarcian/CJV-Command-Line) | Conceptually aligned but undocumented/experimental; no API or template ecosystem. |
| **AI‑Video‑Gen**  [github](https://github.com/Arabianaischool/AI-Video-Gen-by-ARABIAN-AI-SCHOOL) | Python + MoviePy/FFmpeg pipeline | Script text and config  [github](https://github.com/Arabianaischool/AI-Video-Gen-by-ARABIAN-AI-SCHOOL) | Yes (clone & run)  [github](https://github.com/Arabianaischool/AI-Video-Gen-by-ARABIAN-AI-SCHOOL) | Demonstrates automated composition, but not a generic JSON/timeline service. |
| **Remotion**  [github](https://github.com/remotion-dev/remotion) | React framework + render server | React components (code)  [dev](https://dev.to/mayu2008/new-clauderemotion-to-create-amazing-videos-using-ai-37bp) | Yes (OSS) | Excellent engine to build your own service; not JSON/API‑first out of the box. |

***

## Practical Guidance

- If you want **the closest open‑source “service clone”** with JSON timelines and a REST API, start with **Shottower** and adapt its Shotstack JSON schema to your needs; conceptually it’s the nearest to JSON2Video/Creatomate’s backend. [github](https://github.com/shotstack)
- If you want an **agent‑/AI‑first, HTML‑based engine** similar to Creatomate’s layout and animation capabilities, **HyperFrames** is the most modern, actively promoted OSS option, and fits well with your agent stack. [reddit](https://www.reddit.com/r/ClaudeAI/comments/1snkiti/hyperframes_oss_framework_for_ai_agents_to_author/)
- For a **simple, ready‑to‑use API** that already accepts JSON and makes videos, **Video Artist API** is a reasonable starting point, though you should expect to modify/extend it heavily for production. [github](https://github.com/topics/automated-videos)
- For **reference implementations** of JSON‑driven composition you might embed into your own backend, study **story-json-to-video** and **CJV‑Command‑Line**; they’re good “JSON → ffmpeg” pipelines even if they’re not services. [github](https://github.com/ChuckGarcian/CJV-Command-Line)

If you want, I can next help you design a concrete architecture that combines, for example, HyperFrames or Remotion with a JSON schema and API layer that gives you something extremely close to Creatomate/JSON2Video but fully self‑hosted.