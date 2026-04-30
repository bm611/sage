from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import httpx

_TIMEOUT = httpx.Timeout(2.0)
_MODEL_FILE_EXTENSIONS = (".gguf", ".ggml", ".bin", ".safetensors")


@dataclass
class ModelRef:
    id: str
    label: str
    loaded: bool = True  # whether the model is resident in memory / ready to serve
    size_bytes: int | None = None  # on-disk / in-memory footprint, when known


@dataclass
class Server:
    label: str
    base_url: str
    running: bool = False
    models: list[ModelRef] = field(default_factory=list)
    error: str = ""


def _display_model_label(model_id: str) -> str:
    normalized = model_id.replace("\\", "/")
    label = normalized.rsplit("/", 1)[-1]
    lower_label = label.lower()
    for ext in _MODEL_FILE_EXTENSIONS:
        if lower_label.endswith(ext):
            return label[: -len(ext)]
    return label if "/" in normalized else model_id


def _to_model_refs(model_ids: list[str], loaded: bool = True) -> list[ModelRef]:
    return [
        ModelRef(id=model_id, label=_display_model_label(model_id), loaded=loaded)
        for model_id in model_ids
    ]


def _check_ollama(base_url: str) -> tuple[bool, list[ModelRef], str]:
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=_TIMEOUT)
        r.raise_for_status()
        tag_models = r.json().get("models", [])
        sizes = {m["name"]: m.get("size") for m in tag_models}
        model_ids = [m["name"] for m in tag_models]

        # /api/ps lists models currently resident in memory
        loaded_ids: set[str] = set()
        try:
            ps = httpx.get(f"{base_url}/api/ps", timeout=_TIMEOUT)
            ps.raise_for_status()
            loaded_ids = {m["name"] for m in ps.json().get("models", [])}
        except Exception:
            pass

        refs = [
            ModelRef(
                id=mid,
                label=_display_model_label(mid),
                loaded=mid in loaded_ids,
                size_bytes=sizes.get(mid),
            )
            for mid in model_ids
        ]
        return True, refs, ""
    except httpx.ConnectError:
        return False, [], ""
    except Exception as e:
        return False, [], str(e)


def _check_openai_compat(base_url: str) -> tuple[bool, list[ModelRef], str]:
    try:
        r = httpx.get(
            f"{base_url}/v1/models",
            timeout=_TIMEOUT,
            headers={"Authorization": "Bearer not-needed"},
        )
        r.raise_for_status()
        model_ids = [m["id"] for m in r.json().get("data", [])]
        return True, _to_model_refs(model_ids), ""
    except httpx.ConnectError:
        return False, [], ""
    except Exception as e:
        return False, [], str(e)


def _check_lm_studio(base_url: str) -> tuple[bool, list[ModelRef], str]:
    try:
        r = httpx.get(f"{base_url}/api/v0/models", timeout=_TIMEOUT)
        r.raise_for_status()
        refs = [
            ModelRef(
                id=m["id"],
                label=_display_model_label(m["id"]),
                loaded=m.get("state") == "loaded",
            )
            for m in r.json().get("data", [])
            if m.get("type") != "embeddings"
        ]
        return True, refs, ""
    except httpx.ConnectError:
        return False, [], ""
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return _check_openai_compat(base_url)
        return False, [], str(e)
    except Exception as e:
        return False, [], str(e)


def _probe(label: str, base_url: str, fn) -> Server:
    running, models, error = fn(base_url)
    return Server(label=label, base_url=base_url, running=running, models=models, error=error)


def discover() -> tuple[list[Server], list]:
    """
    Probe all local servers concurrently.
    Returns (servers, []) — the empty list is a placeholder kept for API compat.
    """
    probes = [
        ("Ollama",     "http://localhost:11434", _check_ollama),
        ("LM Studio",  "http://localhost:1234",  _check_lm_studio),
        ("llama.cpp",  "http://localhost:8080",  _check_openai_compat),
    ]

    servers: list[Server] = [None] * len(probes)  # type: ignore

    with ThreadPoolExecutor(max_workers=len(probes)) as ex:
        futs = {ex.submit(_probe, *p): i for i, p in enumerate(probes)}
        for fut in as_completed(futs):
            servers[futs[fut]] = fut.result()

    return servers, []
