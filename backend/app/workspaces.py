"""One knowledge database per authenticated company; the embedding model is shared."""

import re
import threading
from dataclasses import replace

from .errors import AppError
from .store import Store


class WorkspaceStores:
    def __init__(self, settings):
        self.settings = settings
        self.root = settings.data_dir / "tenants"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self._stores = {}
        self._lock = threading.Lock()

    def get(self, workspace_id):
        if not re.fullmatch(r"[0-9a-f]{32}", workspace_id):
            raise AppError(403, "invalid_workspace", "Workspace access could not be verified.")
        directory = self.root / workspace_id
        if directory.is_symlink() or directory.resolve().parent != self.root.resolve():
            raise AppError(503, "unsafe_storage", "Workspace storage needs operator attention.")
        with self._lock:
            if workspace_id not in self._stores:
                if len(self._stores) >= self.settings.max_workspaces:
                    raise AppError(503, "workspace_limit", "Workspace capacity needs operator attention.")
                self._stores[workspace_id] = Store(replace(self.settings, data_dir=directory))
            return self._stores[workspace_id]
