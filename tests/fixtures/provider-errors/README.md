# Provider error fixtures

One engine-emitted line per file, copied from real worker logs (Mac `~/ai-workspaces/_artifacts/**/worker.log`, 2026-08/09) unless the name says `SYNTHETIC`.

- Cookies, `cf-ray` and generation ids are replaced with `REDACTED`; an OpenRouter workspace slug is replaced with `example`.
- `*.SYNTHETIC.*`: no real instance has been captured. Built from the real opencode `APIError` shape with a different `statusCode` and message. Replace with a real line when one is seen.
- `*.NEGATIVE.*`: looks like an error but is ordinary tool output; it must classify as `model`.
