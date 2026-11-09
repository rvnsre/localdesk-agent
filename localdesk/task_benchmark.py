"""Opt-in real model benchmark restricted to an isolated Tk test window."""
from __future__ import annotations
import platform
import threading
import time
from dataclasses import replace

import httpx
from .performance import PROFILES, summarize

TASKS = ("click", "type", "scroll", "hotkey", "multi")


def compare(old, new):
    keys = ("model", "base_url", "platform", "display_size", "profile", "iterations", "fixture_version", "cpu_count", "memory_bytes")
    if any(old.get(k) != new.get(k) for k in keys):
        raise ValueError("Reports must use the same model, endpoint, platform, display, profile, iterations, and fixture.")
    if old.get("status") != "completed" or new.get("status") != "completed":
        return {"verified": False, "reason": "Both real task suites must complete."}
    results = {}
    for name in TASKS:
        a, b = old["tasks"][name], new["tasks"][name]
        if b["successes"] < a["successes"] or not a["successes"]:
            results[name] = {"verified": False, "reason": "Success count regressed or baseline had no successes."}
        else:
            results[name] = {"verified": True, "speedup": a["automatic"]["median_ms"] / b["automatic"]["median_ms"]}
    return {"tasks": results, "two_x_verified": all(r.get("verified") and r.get("speedup", 0) >= 2 for r in results.values())}


def run(iterations, profile, backend, engine="optimized"):
    from .config import Settings
    settings = Settings.from_env()
    w, q, tokens = PROFILES[profile]
    settings = replace(settings, profile=profile, capture_backend=backend,
                       screenshot_width=w, screenshot_jpeg_quality=q, max_tokens=tokens)
    import psutil
    report = {"cpu_count": psutil.cpu_count(), "memory_bytes": psutil.virtual_memory().total, "kind": "tasks", "model": settings.model, "base_url": settings.base_url,
              "profile": profile, "platform": platform.platform(), "fixture_version": 1,
              "iterations": iterations, "warmups": 3, "engine": engine, "tasks": {},
              "status": "unavailable", "end_to_end_speedup": None}
    try:
        with httpx.Client(timeout=3, trust_env=False, verify=settings.verify_tls) as client:
            r = client.get(settings.base_url.rstrip("/") + "/models", headers={"Authorization": f"Bearer {settings.api_key}"})
            r.raise_for_status()
    except httpx.HTTPError as exc:
        report["reason"] = f"Model API unavailable: {type(exc).__name__}"
        return report
    import tkinter as tk
    from .agent import Agent
    from .schema import parse_plan
    from .screen import capture_screen, map_plan_to_input
    from .safety import validate_plan, ScreenBounds
    from .automation import Desktop
    from .model import LocalModel

    root = tk.Tk()
    root.title("LocalDesk Benchmark — isolated test window")
    root.geometry("800x620+80+80")
    root.attributes("-topmost", True)
    title = tk.Label(root, font=("Arial", 18), text="LocalDesk Benchmark")
    title.pack(pady=10)
    entry = tk.Entry(root, font=("Arial", 18), width=35)
    entry.pack(pady=10)
    state = {"clicked": False, "submitted": False}
    tk.Button(root, text="Target Button", command=lambda: state.update(clicked=True), font=("Arial", 16)).pack(pady=10)
    tk.Button(root, text="Submit", command=lambda: state.update(submitted=entry.get() == "LocalDesk"), font=("Arial", 16)).pack(pady=10)
    text = tk.Text(root, height=12, width=65)
    text.insert("1.0", "\n".join(f"Scroll row {i}" for i in range(100)))
    text.pack()
    goals = {"click": "In the LocalDesk Benchmark window click Target Button once.",
             "type": "In the LocalDesk Benchmark window click the empty entry and type exactly LocalDesk.",
             "scroll": "In the LocalDesk Benchmark window scroll the text area down.",
             "hotkey": "In the LocalDesk Benchmark window select all text in the entry using the keyboard shortcut.",
             "multi": "In the LocalDesk Benchmark window type LocalDesk in the empty entry, then click Submit."}
    stopped = threading.Event()
    def on_close():
        stopped.set()
        root.withdraw()
    root.protocol("WM_DELETE_WINDOW", on_close)

    def ui(fn):
        event = threading.Event()
        result = []
        def call():
            try:
                result.append(fn())
            finally:
                event.set()
        root.after(0, call)
        if not event.wait(5):
            raise RuntimeError("Fixture UI did not respond.")
        return result[0] if result else None

    def worker():
        agent = None
        try:
            desktop = Desktop(announce=lambda *_: None)
            report["display_size"] = list(desktop.size())
            agent = Agent(settings, desktop)
            if engine == "legacy":
                import requests
                class LegacyModel(LocalModel):
                    def _post(self, url, payload):
                        return self.session.post(url, data=payload, timeout=(5, settings.timeout), verify=settings.verify_tls)
                agent.model.close()
                agent.model = LegacyModel(settings)
                agent.model.session.close()
                agent.model.session = requests.Session()
                agent.model.session.trust_env = False
                agent.model.session.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {settings.api_key}"})
            for name in TASKS:
                samples, stages, errors, successes = [], {}, [], 0
                for index in range(iterations + 3):
                    if stopped.is_set():
                        raise RuntimeError("Benchmark cancelled by user.")
                    def reset():
                        state.update(clicked=False, submitted=False)
                        entry.delete(0, "end")
                        if name == "hotkey":
                            entry.insert(0, "Select this text")
                            entry.focus_force()
                        text.yview_moveto(0)
                        title.config(text=f"Task: {name}")
                        root.lift()
                        return root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height()
                    bounds = ui(reset)
                    time.sleep(.2)
                    started = time.perf_counter()
                    success = False
                    try:
                        if engine == "legacy":
                            frame = capture_screen(w, q, desktop.size())
                            raw = agent.model.plan(goals[name], frame.image_uri, frame.image_width, frame.image_height)
                            plan = validate_plan(map_plan_to_input(parse_plan(raw), frame), ScreenBounds(*desktop.size()), settings)
                        else:
                            plan = agent.propose(goals[name])
                            if not agent.capture.unchanged():
                                raise RuntimeError("Fixture screen changed during planning.")
                        ensure_active(stopped)
                        x, y, width, height = bounds
                        if not plan.steps:
                            raise RuntimeError("Model returned an empty plan.")
                        for action in plan.steps:
                            if action.kind in {"click", "move", "scroll"} and not (x <= action.args["x"] < x + width and y <= action.args["y"] < y + height):
                                raise RuntimeError("Model attempted input outside the test window.")
                            if action.kind == "hotkey" and set(action.args["keys"]) not in ({"ctrl", "a"}, {"command", "a"}, {"cmd", "a"}):
                                raise RuntimeError("Only select-all hotkeys are allowed in this fixture.")
                            if action.kind == "type" and action.args["text"] != "LocalDesk":
                                raise RuntimeError("Unexpected fixture input.")
                        execute_start = time.perf_counter()
                        desktop.execute(plan, settings.max_plan_seconds, cancelled=stopped.is_set)
                        elapsed = time.perf_counter() - started
                        execution = time.perf_counter() - execute_start
                        def verify():
                            return {"click": state["clicked"], "type": entry.get() == "LocalDesk",
                                    "scroll": text.yview()[0] > 0, "hotkey": bool(entry.selection_present()) and entry.index("sel.first") == 0 and entry.index("sel.last") == len(entry.get()),
                                    "multi": state["submitted"]}[name]
                        success = ui(verify)
                        if index >= 3 and success:
                            samples.append(elapsed)
                            current = agent.timings.report() if engine != "legacy" else {}
                            current["execute"] = execution
                            for key, value in current.items():
                                if key != "automatic_total":
                                    stages.setdefault(key, []).append(value)
                    except Exception as exc:
                        if index >= 3:
                            errors.append(type(exc).__name__)
                    if index >= 3:
                        successes += int(success)
                report["tasks"][name] = {"successes": successes, "failures": iterations - successes,
                    "automatic": summarize(samples), "samples_seconds": samples,
                    "stages": {k: summarize(v) for k, v in stages.items()}, "errors": errors,
                    "approval_seconds": 0, "approval_mode": "isolated_fixture_only"}
            report["status"] = "completed"
        except Exception as exc:
            report["reason"] = str(exc)
        finally:
            if agent:
                agent.close()
            root.after(0, root.quit)
    thread = threading.Thread(target=worker, daemon=True)
    root.after(300, thread.start)
    root.mainloop()
    thread.join(5)
    root.destroy()
    return report


def ensure_active(stopped):
    """Do not send input after the fixture closes while a model request is pending."""
    if stopped.is_set():
        raise RuntimeError("Benchmark cancelled by user.")
