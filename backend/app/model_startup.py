"""Server-operator entry point. No services start on import."""
import argparse
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

from app.routing.model_router import ModelRouter, ROOT


def main():
    parser = argparse.ArgumentParser(description="Validate models and start one configured llama-server.")
    parser.add_argument("--model", default="gemma-reasoning")
    parser.add_argument("--llama-server", default=os.getenv("SPEED_LLAMA_SERVER", str(ROOT / "llama.cpp/build/bin/llama-server")))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("server_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    router = ModelRouter()
    for model in router.models.values():
        present = Path(model.model).is_dir() if model.kind == "in_process" else Path(model.model).is_file()
        status = "artifact present; runtime not verified" if present else "unavailable: model artifact not found"
        print(f"[SPEED] {model.name}: {status}")
        if model.kind == "in_process":
            print(f"[SPEED] {model.name}: preloaded during backend startup, device={model.device}, no port")
    model = router.get(args.model)
    if model is None or model.kind != "llama_server":
        parser.error("Select a configured llama_server model")
    if not Path(model.model).is_file():
        parser.error("Required inference model artifact not found; set SPEED_GEMMA_MODEL or update model config")
    if args.validate_only:
        return
    executable = Path(args.llama_server).expanduser().resolve()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        parser.error("llama-server executable unavailable; set SPEED_LLAMA_SERVER")
    url = urlsplit(model.endpoint)
    if url.scheme != "http":
        parser.error("This launcher starts plain HTTP; configure TLS through the existing gateway")
    extra = args.server_args[1:] if args.server_args[:1] == ["--"] else args.server_args
    print(f"[SPEED] {model.name}: starting {model.endpoint}; health is not yet confirmed", flush=True)
    sys.stdout.flush()
    os.execv(str(executable), [str(executable), "--model", model.model, "--alias", model.model_id,
                             "--host", url.hostname, "--port", str(url.port or 80),
                             *extra])


if __name__ == "__main__":
    main()
