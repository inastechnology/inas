import fcntl
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from functools import wraps

_locks_guard = threading.Lock()
_path_locks: dict[str, threading.RLock] = {}


def atomic_write_json(path: str, value, *, indent: int | None = 2):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False) as file:
            temporary_path = file.name
            json.dump(value, file, ensure_ascii=True, indent=indent)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def serialized_repository_write(path_attribute: str):
    """Reload, mutate, and atomically save a JSON repository under one host lock."""

    def decorate(method):
        @wraps(method)
        def wrapped(repository, *args, **kwargs):
            path = os.path.abspath(getattr(repository, path_attribute))
            state = _repository_state(repository)
            if getattr(state, "write_depth", 0):
                return method(repository, *args, **kwargs)
            with repository_file_lock(path):
                state.write_depth = 1
                repository.load()
                try:
                    return method(repository, *args, **kwargs)
                except Exception:
                    repository.load()
                    raise
                finally:
                    state.write_depth = 0

        return wrapped

    return decorate


def _repository_state(repository):
    state = getattr(repository, "_json_repository_io_state", None)
    if state is not None:
        return state
    with _locks_guard:
        state = getattr(repository, "_json_repository_io_state", None)
        if state is None:
            state = threading.local()
            repository._json_repository_io_state = state
    return state


@contextmanager
def repository_file_lock(path: str):
    with _locks_guard:
        thread_lock = _path_locks.setdefault(path, threading.RLock())
    with thread_lock:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(f"{path}.lock", "a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
