"""Compare persistent Requests and HTTPX clients against a loopback fixture."""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import orjson
from .performance import summarize


def run(iterations):
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("Install the benchmark extra for the legacy Requests comparison.") from exc

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            data = b'{"choices":[{"message":{"content":"ok"}}]}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = {}
    payload = orjson.dumps({"model": "fixture", "image": "a" * 100000})
    try:
        for name, factory in (("requests", requests.Session), ("httpx", lambda: httpx.Client(trust_env=False))):
            with factory() as client:
                samples = []
                for index in range(iterations + 3):
                    start = time.perf_counter()
                    kwargs = {"data" if name == "requests" else "content": payload}
                    response = client.post(f"http://127.0.0.1:{server.server_port}/", timeout=5, **kwargs)
                    response.raise_for_status()
                    orjson.loads(response.content)
                    if index >= 3:
                        samples.append(time.perf_counter() - start)
                results[name] = {**summarize(samples), "samples_seconds": samples}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
    return {"kind": "transport_loopback", "iterations": iterations, "warmups": 3,
            "results": results, "end_to_end_speedup": None,
            "note": "Synthetic HTTP fixture; not a vision-model or task-speed measurement."}
