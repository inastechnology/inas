import fcntl
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from ina_edge_runtime import NodeType, generate_node_id, parse_node_id


def load_edge_identity(path: str | os.PathLike[str]) -> str:
    identity_path = Path(path)
    try:
        document = json.loads(identity_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Edge identity is not provisioned: {identity_path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Edge identity file is invalid JSON: {identity_path}") from exc
    if not isinstance(document, dict) or set(document) != {"schema_version", "node_id", "node_type"} or document.get("schema_version") != 1:
        raise RuntimeError(f"Edge identity file has an unsupported schema: {identity_path}")
    identity = parse_node_id(document.get("node_id"))
    if identity.node_type != NodeType.EDGE_GATEWAY or document.get("node_type") != NodeType.EDGE_GATEWAY.value:
        raise RuntimeError(f"Edge identity file does not contain an Edge Gateway identity: {identity_path}")
    return identity.value


def bootstrap_development_identity(path: str | os.PathLike[str]) -> str:
    identity_path = Path(path)
    identity_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = identity_path.with_suffix(f"{identity_path.suffix}.lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        if identity_path.exists():
            return load_edge_identity(identity_path)
        node_id = generate_node_id(NodeType.EDGE_GATEWAY)
        document = {
            "schema_version": 1,
            "node_id": node_id,
            "node_type": NodeType.EDGE_GATEWAY.value,
        }
        temporary_path = ""
        try:
            with NamedTemporaryFile("w", encoding="utf-8", dir=identity_path.parent, delete=False) as file:
                temporary_path = file.name
                json.dump(document, file, ensure_ascii=True, separators=(",", ":"))
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, identity_path)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)
        return node_id
