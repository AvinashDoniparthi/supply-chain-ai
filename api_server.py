import argparse
import io
import json
import logging
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Tuple

from main import run_analysis

logger = logging.getLogger(__name__)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return bool(value)


def _analysis_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "max_depth": int(payload.get("max_depth", 3)),
        "max_candidates_per_company": int(payload.get("max_candidates_per_company", 5)),
        "timeout_seconds": int(payload.get("timeout_seconds", 180)),
        "skip_risk": _as_bool(payload.get("skip_risk", False)),
        "skip_news": _as_bool(payload.get("skip_news", False)),
        "supplier_cache_enabled": _as_bool(payload.get("supplier_cache_enabled", True), True),
        "refresh_supplier_cache": _as_bool(payload.get("refresh_supplier_cache", False)),
        "supplier_cache_only": _as_bool(payload.get("supplier_cache_only", False)),
        "execution_mode": str(payload.get("execution_mode", "llm")),
    }


def run_analysis_request(
    payload: Dict[str, Any],
    runner: Callable[..., Any] = run_analysis,
) -> Tuple[int, Dict[str, Any]]:
    company = str(payload.get("company") or payload.get("company_name") or "").strip()
    if not company:
        return 400, {"ok": False, "error": "company is required"}

    kwargs = _analysis_kwargs(payload)
    stdout_buffer = io.StringIO()
    try:
        with redirect_stdout(stdout_buffer):
            state = runner(company, **kwargs)
    except Exception as exc:
        logger.exception("Analysis request failed")
        return 500, {"ok": False, "error": str(exc)}

    response = {
        "ok": True,
        "company": company,
        "result": _jsonable(state),
    }
    return 200, response


class AnalysisRequestHandler(BaseHTTPRequestHandler):
    server_version = "SupplyChainAI/1.0"

    def _set_headers(self, status_code: int = 200) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _write_json(self, status_code: int, payload: Dict[str, Any]) -> None:
        self._set_headers(status_code)
        self.wfile.write(json.dumps(payload, indent=2).encode("utf-8"))

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._set_headers(204)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in {"", "/health"}:
            self._write_json(
                200,
                {
                    "ok": True,
                    "status": "healthy",
                    "service": "supply-chain-ai",
                },
            )
            return

        self._write_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/analyze":
            self._write_json(404, {"ok": False, "error": "not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length) if content_length else b"{}"
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except Exception:
            self._write_json(400, {"ok": False, "error": "invalid JSON body"})
            return

        status_code, response = run_analysis_request(payload)
        self._write_json(status_code, response)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Supply Chain AI HTTP server")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind.")
    return parser


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), AnalysisRequestHandler)
    logger.info("Serving supply-chain API on http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server")
    finally:
        server.server_close()


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
