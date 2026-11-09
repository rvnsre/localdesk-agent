"""Diagnostic CLI commands; existing task syntax remains compatible."""
from pathlib import Path
import platform
import time

import orjson
import typer
from rich.console import Console

from .performance import doctor as diagnostics, summarize, PROFILES

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json")):
    """Inspect dependency versions, resources, and local API connectivity."""
    import httpx
    from .config import Settings
    report = diagnostics()
    settings = Settings.from_env()
    try:
        with httpx.Client(trust_env=False, verify=settings.verify_tls, timeout=3) as client:
            response = client.get(settings.base_url.rstrip("/") + "/models",
                                  headers={"Authorization": f"Bearer {settings.api_key}"})
            response.raise_for_status()
            report["api"] = "available"
    except httpx.HTTPError as exc:
        report["api"] = "unavailable"
        report["api_error"] = type(exc).__name__
    if json_output:
        print(orjson.dumps(report, option=orjson.OPT_INDENT_2).decode())
    else:
        console.print(report)


@app.command()
def benchmark(iterations: int = typer.Option(20, min=3, max=500),
              profile: str = "balanced", capture_backend: str = "auto",
              output: Path = Path("benchmark.json"),
              mode: str = typer.Option("capture", help="capture, transport, or tasks"),
              baseline: Path | None = None,
              engine: str = "optimized"):
    if engine not in {"legacy", "optimized"}:
        raise typer.BadParameter("Engine must be legacy or optimized")
    """Write real timings. Task mode operates only the bundled isolated test window."""
    if profile not in PROFILES or capture_backend not in {"auto", "mss", "dxcam", "pyautogui"}:
        raise typer.BadParameter("Unknown profile or capture backend")
    if mode == "transport":
        from .transport_benchmark import run
        report = run(iterations)
    elif mode == "tasks":
        from .task_benchmark import run
        report = run(iterations, profile, capture_backend, engine)
    elif mode == "capture":
        from .capture import CaptureSession
        from .screen import capture_screen
        from .automation import Desktop
        size = Desktop().size()
        width, quality, _ = PROFILES[profile]
        report = {"kind": "capture", "profile": profile, "platform": platform.system(),
                  "iterations": iterations, "warmups": 3, "input_size": list(size), "results": {},
                  "end_to_end_speedup": None}
        with CaptureSession(capture_backend) as session:
            for name, capture in (("legacy", lambda: capture_screen(width, quality, size)),
                                  ("optimized", lambda: session.capture(width, quality, size))):
                samples = []
                try:
                    for index in range(iterations + 3):
                        start = time.perf_counter()
                        frame = capture()
                        elapsed = time.perf_counter() - start
                        if index >= 3:
                            samples.append(elapsed)
                    report["results"][name] = {**summarize(samples), "samples_seconds": samples, "backend": frame.backend}
                except Exception as exc:
                    report["results"][name] = {"unavailable": type(exc).__name__}
            if all("median_ms" in report["results"].get(n, {}) for n in ("legacy", "optimized")):
                report["capture_speedup"] = report["results"]["legacy"]["median_ms"] / report["results"]["optimized"]["median_ms"]
    else:
        raise typer.BadParameter("Mode must be capture, transport, or tasks")
    if baseline is not None:
        old = orjson.loads(baseline.read_bytes())
        if report["kind"] != "tasks" or old.get("kind") != "tasks":
            raise typer.BadParameter("Baseline comparison requires task reports")
        from .task_benchmark import compare
        report["comparison"] = compare(old, report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(orjson.dumps(report, option=orjson.OPT_INDENT_2))
    console.print(report)
    console.print(f"Report: {output}")


if __name__ == "__main__":
    app()
