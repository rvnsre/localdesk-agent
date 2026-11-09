# Benchmark methodology

## Scope

Capture reports measure screenshot plus image encoding. Transport reports use a synthetic loopback HTTP fixture with both clients kept alive. Neither establishes vision-model latency or end-to-end speedup. Raw reports contain timings and environment metadata, never screenshots, prompts, clipboard content or API keys.

## Real task benchmark

Install `.[benchmark]`, start the same vision model/API used by the baseline, and run the commands below **from an interactive desktop session**. Tkinter must be installed. The command opens an isolated, topmost LocalDesk Benchmark window. Keep it unobstructed and do not use the mouse/keyboard during the run. Closing that window cancels the suite. It permits input only inside that window, select-all hotkeys, and the fixed text `LocalDesk`.

```bash
localdesk benchmark --mode tasks --engine legacy --iterations 20 --output baseline.json
localdesk benchmark --mode tasks --engine optimized --iterations 20 --baseline baseline.json --output optimized.json
```

Each engine runs three warmups then twenty measured trials for click, type, scroll, select-all hotkey, and multi-step submit tasks. The legacy engine reconstructs the v0.1 capture and persistent Requests paths; it is a benchmark adapter, not an independent checkout of the old release. Balanced uses the original image and token settings. For an exact release comparison, run the archived v0.1 checkout with an equivalent fixture runner.

Reports compare only matching endpoint/model identifiers, platform, CPU count, RAM, display size, profile, fixture version and iteration count. Keep the actual model weights, quantization, server settings, GPU, power mode and load unchanged; identifiers alone cannot establish hardware or model equivalence. Repeat in reversed engine order to assess thermal/load bias.

Automatic total includes planning, validation, freshness guard (optimized), and input execution. Human approval is excluded and recorded as zero because pre-approval applies only to this restricted test fixture. Per-stage timings are available for the optimized engine. Successful trials determine timing statistics; failures and errors are counted separately. A 2x claim requires at least 2x median improvement in all five tasks without a lower success count; no successful baseline means no verified comparison.

## Current validation host

Fifty unit/integration tests passed on Windows/Python 3.11. The capture report measured 63.06 ms original versus 40.91 ms optimized median (1.54x) in this session, with 20 trials per path. Both capture and loopback measurements ran while other validation processes were active; they are host observations, not controlled laboratory results. The host supplied OpenCV 5.0 through its existing opencv-python installation; clean CI installs the declared headless distribution.

The local model endpoint on port 1234 was unavailable. End-to-end task speedup remains unverified. GUI capture and synthetic transport results, when available, are specific to this host. CI uses mocked input; it is not real desktop validation on macOS/Linux.

## Artwork

`python tools/render_readme.py` regenerates SVG and PNG README panels from the same scene. The performance panel reads capture-windows.json; the terminal panel is clearly labeled illustrative.
