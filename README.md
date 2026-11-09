# LocalDesk Agent

LocalDesk Agent is a terminal-based desktop automation tool. A local multimodal AI model inspects a screenshot and proposes mouse and keyboard actions. The program validates the plan and shows every action before asking for approval.

Python 3.10 or newer is required. Windows, macOS, and Linux are supported. Linux works best with X11; Wayland compositors may restrict screen capture and input control.

## See LocalDesk

![LocalDesk Agent: local vision, deliberate action](docs/assets/01-hero.png)
![Execution workflow: capture, model, validate, approve, execute](docs/assets/02-workflow.png)
![Windows, macOS and Linux capture architecture](docs/assets/03-platforms.png)
![Measured capture timings and unverified end-to-end target](docs/assets/04-performance.png)
![Illustrative terminal demo, not a real benchmark capture](docs/assets/05-terminal.png)

## Safety

- The default API address is loopback (`127.0.0.1`). Remote API hosts require explicit opt-in.
- Model output must be valid JSON and pass action, coordinate, duration, and text limits.
- Plans are shown for approval before any input is sent. `--yes` bypasses the approval prompt.
- Shell-like text and system-level hotkeys are blocked. Plans are never executed as shell commands.
- PyAutoGUI's fail-safe is enabled. Move the pointer to the upper-left corner to stop an active sequence.
- The default PyAutoGUI per-action pause is disabled. Only validated move and wait durations add delays.
- Screenshots are sent to the configured model API. Use a local endpoint when screen contents must stay on the device.
- Unicode and multiline typing temporarily use the system clipboard and restore its previous text. Rich, non-text clipboard formats may not be preserved.

## Install

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS or Linux
source .venv/bin/activate
python -m pip install -e .
```

The runtime calibrates available DXcam (Windows), MSS and ImageGrab capture paths on this device, and caches only the selected backend name for one day. Capture sessions reuse native resources. NumPy/OpenCV resize and encode the image; Pillow remains the encoding fallback. `pybase64` and `orjson` handle transport encoding. Calibration includes JPEG encoding, not capture alone.

The runtime has 22 direct dependencies on Windows and 21 on macOS/Linux. Each has a concrete role; see [the dependency map](docs/DEPENDENCIES.md). Library count is not a performance guarantee.

## Configure a local model

Start an OpenAI-compatible API server with a vision-capable model. For example, LM Studio may expose `http://127.0.0.1:1234/v1`. The model server must accept image input and JSON mode (`response_format: {"type":"json_object"}`).

PowerShell:

```powershell
$env:LOCALDESK_MODEL = "qwen2.5-vl"
$env:LOCALDESK_BASE_URL = "http://127.0.0.1:1234/v1"
```

macOS/Linux:

```bash
export LOCALDESK_MODEL="qwen2.5-vl"
export LOCALDESK_BASE_URL="http://127.0.0.1:1234/v1"
```

## Run

```bash
localdesk "Open a new browser tab"
localdesk --dry-run "Type LocalDesk into the search field"
localdesk
```

The interactive mode accepts one task at a time; use `/quit` to exit. `--dry-run` displays the proposed plan without sending input. Review each action before approving it.

## CLI options

| Option | Description |
| --- | --- |
| `--dry-run` | Generate and display a plan without executing it. |
| `--yes` | Execute the validated plan without an approval prompt. |
| `--show-config` | Print the effective API URL, model, and step limit. |
| `--version` | Print the installed version. |

## Configuration

| Environment variable | Default | Description |
| --- | --- | --- |
| `LOCALDESK_BASE_URL` | `http://127.0.0.1:1234/v1` | OpenAI-compatible API base URL. |
| `LOCALDESK_MODEL` | `local-model` | Model ID exposed by the server. |
| `LOCALDESK_API_KEY` | `local` | API key; set an empty value if the local server does not use authentication. |
| `LOCALDESK_TIMEOUT` | `90` | API response timeout in seconds. |
| `LOCALDESK_TEMPERATURE` | `0.1` | Generation temperature, from 0 to 2. |
| `LOCALDESK_VERIFY_TLS` | `true` | Verify HTTPS certificates. |
| `LOCALDESK_MAX_STEPS` | `12` | Maximum actions in one plan. |
| `LOCALDESK_MAX_TEXT_CHARS` | `2000` | Maximum characters in one typing action. |
| `LOCALDESK_MAX_GOAL_CHARS` | `4000` | Maximum characters in a user task. |
| `LOCALDESK_MAX_SECONDS` | `120` | Estimated and actual action-sequence time limit. |
| `LOCALDESK_SCREENSHOT_WIDTH` | `1280` | Maximum screenshot width sent to the model. |
| `LOCALDESK_JPEG_QUALITY` | `65` | JPEG quality, from 20 to 95. |
| `LOCALDESK_ALLOW_REMOTE_API` | `false` | Allow a non-loopback API host. |
| `LOCALDESK_ALLOW_SHELL_TEXT` | `false` | Disable the shell-like text filter. |

## Tests and performance

```bash
python -m unittest discover -v
localdesk-benchmark-screenshot --iterations 15
```

The test suite covers configuration, plan parsing, safety checks, coordinate mapping, API errors, a loopback HTTP round trip, console handling, and mocked desktop actions. The screenshot benchmark reports capture-only and full JPEG/base64 timings for the current desktop. Results vary by operating system, display permissions, and hardware.

## Platform notes

- **Windows:** DXcam requires access to the active desktop. If DXGI is unavailable, the program switches to ImageGrab and then MSS.
- **macOS:** Terminal or Python may need Accessibility and Screen Recording permissions.
- **Linux:** X11/XWayland is the preferred backend. Wayland may block capture or input. Unicode clipboard typing may require `xclip`, `xsel`, or `wl-clipboard`.

## Limitations

The model can misread interface elements. Inspect the plan, especially before actions that submit, delete, share, purchase, or change account settings. The application stops if the screenshot and input coordinate aspect ratios do not match. For multi-monitor setups, the primary monitor is used.

## Performance profiles and diagnostics

```bash
localdesk --profile fast --capture-backend auto "Find the search field"
localdesk --profile quality --dry-run "Read the small toolbar labels"
localdesk doctor --json
localdesk benchmark --mode capture --iterations 20 --output capture.json
python -m pip install ".[benchmark]"
localdesk benchmark --mode transport --output transport.json
```

| Profile | Maximum image width | JPEG quality | Response token limit |
| --- | ---: | ---: | ---: |
| balanced | 1280 | 65 | 900 |
| fast | 960 | 60 | 600 |
| quality | 1920 | 85 | 1200 |

`LOCALDESK_PROFILE`, `LOCALDESK_CAPTURE_BACKEND`, and `LOCALDESK_MAX_TOKENS` set defaults. Existing screenshot width and quality environment variables override profile values. An explicit CLI profile selects all three profile values. The fast profile retries an **empty** plan once with a quality image; it cannot detect every model misreading and does not promise accuracy equivalence.

Plans are rejected if **any pixel changes** between capture and execution. This conservative guard can reject animated pages, clocks, blinking cursors, or a terminal that prints the plan on the captured display. Keep the CLI on another display or use dry-run review while preparing a stable target. A new plan and approval are required after rejection. Pixel equality is a freshness guard, not proof that a model plan is correct.

The optional `wait_change(timeout)` plan action waits for a screen change with a bounded deadline. Explicit `wait(seconds)` delays are preserved. Input remains sequential. A cancelled asynchronous model request discards its result immediately; its worker network request can continue until the HTTP timeout and never executes input. Read timeouts and desktop actions are never automatically retried.

See [benchmark methodology and limitations](docs/benchmarks/README.md), [raw capture measurements](docs/benchmarks/capture-windows.json), and [transport comparison](docs/benchmarks/transport-windows.json). The 2x end-to-end target has **not been verified** because the local vision API was unavailable on the validation host.

## Cancellation and repeated waits

Each successful `wait_change` consumes that observed change: a second wait requires a newer frame. Timeouts and poll intervals must be positive and finite. Embedded callers can pass `cancelled=callback` to `Desktop.execute`; cancellation is checked before each input action. The isolated benchmark also rejects a late model result when its window has been closed. Diagnostic tracebacks do not print local variable values.
