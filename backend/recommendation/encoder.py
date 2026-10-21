"""Offline-only MiniLM ONNX CPU adapter. Importing the host loads no ML runtime."""
import hashlib
import importlib.util
from importlib.metadata import version as package_version
from pathlib import Path
from threading import RLock

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
PREPROCESSING_VERSION = "fastembed-0.9.0:minilm-mean-l2:nfc-strip:256tokens:v1"


class MiniLMEncoder:
    dimension = 384

    def __init__(self, model_dir):
        self.model_dir = Path(model_dir)
        self.version = "minilm:unavailable"
        self.error = None
        self._model = None
        self._tokenizer = None
        self._directory = None
        self._signature = None
        self._runtime_error = None
        self._lock = RLock()

    def _files(self):
        directory = self.model_dir
        paths = [directory / name for name in ("model.onnx", "tokenizer.json", "config.json", "tokenizer_config.json", "special_tokens_map.json")]
        if not all(path.is_file() for path in paths):
            raise RuntimeError("Offline MiniLM model/tokenizer files are incomplete")
        return directory, paths

    def available(self):
        with self._lock:
            try:
                for package in ("numpy", "fastembed", "tokenizers", "onnxruntime"):
                    if importlib.util.find_spec(package) is None:
                        raise RuntimeError("Missing recommendation dependency: " + package)
                directory, paths = self._files()
                signature = tuple((str(path), path.stat().st_size, path.stat().st_mtime_ns) for path in paths)
                if signature != self._signature:
                    digest = hashlib.sha256(PREPROCESSING_VERSION.encode("utf-8"))
                    for package in ("fastembed", "tokenizers", "onnxruntime"):
                        digest.update((package + "=" + package_version(package)).encode("utf-8"))
                    for path in paths:
                        digest.update(path.name.encode("utf-8"))
                        with path.open("rb") as handle:
                            for block in iter(lambda: handle.read(1024 * 1024), b""):
                                digest.update(block)
                    version = "minilm:" + digest.hexdigest()
                    if self._model is not None and version != self.version:
                        raise RuntimeError("MiniLM files changed; restart before using a new model version")
                    if version != self.version:
                        self._tokenizer = None
                    self.version = version
                    self._signature = signature
                    self._directory = directory
                    self._runtime_error = None
                if self._runtime_error:
                    raise RuntimeError(self._runtime_error)
                self.error = None
                return True
            except (ImportError, OSError, ValueError, RuntimeError) as error:
                self.error = str(error)
                return False

    def encode(self, texts):
        with self._lock:
            if not self.available():
                raise RuntimeError(self.error or "MiniLM is unavailable")
            if not texts:
                return []
            try:
                if self._tokenizer is None:
                    from tokenizers import Tokenizer
                    self._tokenizer = Tokenizer.from_file(str(self._directory / "tokenizer.json"))
                    self._tokenizer.no_truncation()
                    self._tokenizer.no_padding()
            except Exception as error:
                self._runtime_error = "Offline MiniLM tokenizer failed: " + str(error)
                self.error = self._runtime_error
                raise RuntimeError(self.error) from error
            for text in texts:
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Encoder input must be non-empty text")
                if len(self._tokenizer.encode(text).ids) > 256:
                    raise ValueError("MiniLM term exceeds 256 tokens; split the base term explicitly")
            try:
                if self._model is None:
                    from fastembed import TextEmbedding
                    self._model = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(self.model_dir),
                                                threads=2, providers=["CPUExecutionProvider"],
                                                local_files_only=True, specific_model_path=str(self._directory))
                return list(self._model.embed(texts, batch_size=64))
            except Exception as error:
                self._runtime_error = "Offline MiniLM inference failed: " + str(error)
                self.error = self._runtime_error
                raise RuntimeError(self.error) from error
