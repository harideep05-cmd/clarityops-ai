import hashlib
import json
import threading

import numpy as np

from .config import MODEL_FILES, MODEL_NAME, MODEL_REVISION, Settings
from .errors import AppError


class LocalEmbeddings:
    def __init__(self, settings: Settings):
        self.directory = settings.data_dir / "embedding-model"
        self._model = None
        self._lock = threading.Lock()
        self.model_id = None

    def load(self):
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            try:
                # Pre-download explicitly; requests must never hang on model downloads.
                manifest = json.loads((self.directory / "manifest.json").read_text())
                if (
                    manifest["model"] != MODEL_NAME
                    or manifest["revision"] != MODEL_REVISION
                    or set(manifest["files"]) != MODEL_FILES
                ):
                    raise ValueError("Model mismatch")
                for filename, checksum in manifest["files"].items():
                    if hashlib.sha256((self.directory / filename).read_bytes()).hexdigest() != checksum:
                        raise ValueError("Model checksum mismatch")
                from fastembed import TextEmbedding

                self._model = TextEmbedding(
                    MODEL_NAME,
                    specific_model_path=str(self.directory),
                    local_files_only=True,
                    threads=2,
                )
                self.model_id = MODEL_NAME + ":" + MODEL_REVISION
            except Exception:
                raise AppError(
                    503,
                    "embedding_unavailable",
                    "Local search is not ready. Run the embedding setup command on the server.",
                ) from None

    def embed(self, texts, query=False):
        self.load()
        try:
            # Work on a separate tokenizer to avoid mutation while requests run.
            from tokenizers import Tokenizer

            tokenizer = Tokenizer.from_file(str(self.directory / "tokenizer.json"))
            tokenizer.no_truncation()
            if any(len(tokenizer.encode(t).ids) > 480 for t in texts):
                raise AppError(
                    422,
                    "text_too_dense",
                    "Some text exceeds the search model's context. Use an English text PDF with shorter sections or a shorter question.",
                )
            method = self._model.query_embed if query else self._model.passage_embed
            vectors = np.asarray(list(method(texts)), dtype="<f4")
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            if not np.isfinite(vectors).all() or np.any(norms == 0):
                raise ValueError("Invalid vectors")
            return vectors / norms
        except AppError:
            raise
        except Exception:
            raise AppError(
                503, "embedding_failed", "Local search could not process the text. Please retry."
            ) from None


def retrieve(question, store, embeddings, settings):
    rows = store.all_chunks()
    if not rows:
        return []
    query = embeddings.embed([question], query=True)[0]
    if any(r["embedding_model"] != embeddings.model_id for r in rows):
        raise AppError(
            409, "index_model_mismatch", "The search model changed. Remove and re-upload indexed documents."
        )
    matrix = np.stack([np.frombuffer(r["embedding"], dtype="<f4") for r in rows])
    if matrix.shape[1] != len(query) or not np.isfinite(matrix).all():
        raise AppError(503, "index_invalid", "The document index could not be read.")
    scores = matrix @ query
    minimum_score = max(settings.retrieval_threshold, float(scores.max()) - 0.10)
    results = []
    for index in np.argsort(-scores, kind="stable"):
        score, row = float(scores[index]), rows[index]
        if score < minimum_score:
            break
        # Avoid near-identical overlapping chunks using up the small evidence budget.
        if any(
            r["document_id"] == row["document_id"]
            and r["page"] == row["page"]
            and min(r["char_end"], row["char_end"]) - max(r["char_start"], row["char_start"])
            > 0.65 * min(len(r["text"]), len(row["text"]))
            for r in results
        ):
            continue
        results.append(
            {k: v for k, v in row.items() if k not in ("embedding", "embedding_model")}
            | {"score": round(score, 4), "source_id": f"S{len(results) + 1}"}
        )
        if len(results) == settings.top_k:
            break
    return results
