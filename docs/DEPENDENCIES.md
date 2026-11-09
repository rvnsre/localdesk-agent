# Runtime dependency map

All packages below are used by runtime features. DXcam is conditional on Windows; the other 21 are cross-platform requirements. Version ranges are declared in pyproject.toml.

| Library | Runtime responsibility |
| --- | --- |
| httpx | Persistent model client, timeouts and TLS |
| anyio | Cancellable asynchronous planner facade |
| tenacity | Two bounded retries for connection establishment only |
| numpy | Pixel buffers |
| opencv-python-headless | Image downscaling, color conversion and JPEG encoding |
| Pillow | Capture conversion and JPEG fallback |
| mss | Reusable primary-display capture |
| dxcam | Windows Desktop Duplication capture |
| pybase64 | Fast JPEG base64 encoding |
| xxhash | In-memory full-frame freshness digest |
| orjson | Model payloads, plans and benchmark reports |
| pydantic | Strict model-plan envelope validation |
| pydantic-settings | Runtime profile and environment settings |
| PyAutoGUI | Mouse and keyboard execution, fail-safe, fallback capture |
| pyperclip | Unicode clipboard input with text restoration |
| typer | Doctor and benchmark command interface |
| rich | Terminal report presentation |
| platformdirs | Per-user calibration cache location |
| diskcache | Expiring backend selection metadata |
| filelock | Serialize calibration across local processes |
| psutil | Runtime resource and benchmark environment diagnostics |
| packaging | Installed dependency version compatibility checks |

Requests is an optional benchmark dependency used only to compare the previous persistent transport and legacy task engine. It is not installed in the base runtime.
