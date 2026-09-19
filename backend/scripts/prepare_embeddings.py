"""Explicit one-time, revision-pinned model download. No company data is sent."""

import hashlib
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import MODEL_FILES, MODEL_NAME, MODEL_REVISION, Settings  # noqa: E402


def prepare():
    directory = Settings.from_env().data_dir / "embedding-model"
    directory.mkdir(parents=True, exist_ok=True)
    checksums = {}
    for filename in sorted(MODEL_FILES):
        destination = directory / filename
        temporary = destination.with_suffix(destination.suffix + ".download")
        print(f"Preparing {filename}", flush=True)
        url = f"https://huggingface.co/qdrant/bge-small-en-v1.5-onnx-q/resolve/{MODEL_REVISION}/{filename}"
        try:
            with requests.get(url, stream=True, timeout=(15, 60)) as response:
                response.raise_for_status()
                with temporary.open("wb") as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        stream.write(chunk)
            os.replace(temporary, destination)
            checksums[filename] = hashlib.sha256(destination.read_bytes()).hexdigest()
        finally:
            temporary.unlink(missing_ok=True)
    manifest = {"model": MODEL_NAME, "revision": MODEL_REVISION, "files": checksums}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    from app.embeddings import LocalEmbeddings

    embeddings = LocalEmbeddings(Settings.from_env())
    vector = embeddings.embed(["Local company document search"])
    print(f"Ready: {vector.shape[1]} dimensions. Embeddings run locally.")


if __name__ == "__main__":
    prepare()
