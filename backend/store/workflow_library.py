"""Local API workflow templates, independent of configured generation backends."""
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import unicodedata
import uuid


from ..domain import BackendError, ConflictError, NotFoundError, ValidationError

MAX_BYTES = 8 * 1024 * 1024
IDENTIFIER = re.compile(r"[0-9a-f]{32}\Z")
CONTENT_FIELDS = ("workflow", "bindings", "output_nodes")


def normal_name(value):
    return unicodedata.normalize("NFKC", value).casefold()


def workflow_name(value):
    if (not isinstance(value, str) or not 1 <= len(value.strip()) <= 120
            or any(c in '/\\:<>"|?*' or unicodedata.category(c).startswith("C") for c in value)
            or value.strip() in {".", ".."}):
        raise ValidationError("工作流名称须为 1 至 120 个字符，不能包含路径、控制字符或文件名保留符号。")
    return value.strip()


def decode(raw):
    def constant(value):
        raise ValidationError("JSON 不允许 NaN 或 Infinity。")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValidationError("JSON 不允许重复字段。")
            result[key] = value
        return result
    try:
        result = json.loads(raw.decode("utf-8-sig"), parse_constant=constant, object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValidationError("工作流 JSON 内容无效。") from exc
    if not isinstance(result, dict):
        raise ValidationError("工作流请求须为 JSON 对象。")
    return result


class WorkflowLibrary:
    def __init__(self, directory, validator):
        self.directory = Path(directory).resolve()
        self.validator = validator
        # Reads cannot expose a newly written template before its backend save
        # succeeds, and all writers share the on-disk process lock below.
        self._lock = threading.RLock()

    def _path(self, identifier):
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
            raise ValidationError("无效的工作流 ID。")
        path = self.directory / (identifier + ".json")
        if not path.resolve().is_relative_to(self.directory):
            raise ValidationError("工作流文件必须位于工作流目录。")
        return path

    def _validate(self, document, identifier):
        if not isinstance(document, dict):
            raise ValidationError("工作流须为 JSON 对象。")
        name = workflow_name(document.get("name"))
        try:
            checked = self.validator({"id": identifier, "name": name, "kind": "comfyui",
                                        "base_url": "http://127.0.0.1:8188",
                                        "workflow": document.get("workflow"),
                                        "bindings": document.get("bindings"),
                                        "output_nodes": document.get("output_nodes", [])})
        except BackendError as exc:
            raise ValidationError(str(exc)) from exc
        return {"id": identifier, "name": name, "workflow": checked["workflow"],
                "bindings": checked["bindings"], "output_nodes": checked["output_nodes"]}

    def read(self, identifier):
        with self._lock:
            return self._read(identifier)

    def _read(self, identifier):
        path = self._path(identifier)
        try:
            with path.open("rb") as handle:
                raw = handle.read(MAX_BYTES + 1)
        except FileNotFoundError:
            return None
        if len(raw) > MAX_BYTES:
            raise ValidationError("工作流模板超过 8 MB。")
        record = decode(raw)
        if record.get("id") != identifier:
            raise ValidationError("工作流文件的 ID 与文件名不匹配。")
        return dict(self._validate(record, identifier), revision=hashlib.sha256(raw).hexdigest())

    def listing(self):
        with self._lock:
            return self._listing()

    def _listing(self):
        if not self.directory.is_dir():
            return []
        records = []
        for path in self.directory.iterdir():
            if path.is_file() and path.suffix == ".json" and IDENTIFIER.fullmatch(path.stem):
                record = self.read(path.stem)
                if record:
                    records.append({key: record[key] for key in ("id", "name", "revision")})
        return sorted(records, key=lambda item: (item["name"].casefold(), item["id"]))

    def save_as(self, document):
        identifier = uuid.uuid4().hex
        record = self._validate(document, identifier)
        with self._writing():
            if any(normal_name(item["name"]) == normal_name(record["name"]) for item in self.listing()):
                raise ConflictError("工作流名称已存在，请使用新名称。")
            return self._write(record)

    def save_and_apply(self, document, backend, save_backend):
        """Save a named template and backend in one visible operation.

        Selected templates retain their ID and use optimistic revision checks.
        Previous bytes are backed up before replacement, and restored if the
        backend transaction fails. New identical named templates are reused.
        """
        identifier = uuid.uuid4().hex
        record = self._validate(document, identifier)
        with self._writing():
            source_id = document.get("workflow_id")
            source = None
            if source_id is not None:
                source = self.read(source_id)
                if source is None:
                    raise NotFoundError("所选工作流已不存在，请重新选择。")
                if document.get("workflow_revision") != source["revision"]:
                    raise ConflictError("所选工作流已变化，请重新选择后保存。")
                record["id"] = source_id
            elif document.get("workflow_revision") is not None:
                raise ValidationError("工作流修订号需要对应的工作流 ID。")

            existing = next((item for item in self.listing()
                             if item["id"] != source_id
                             and normal_name(item["name"]) == normal_name(record["name"])), None)
            previous = None
            created = source is None and existing is None
            if existing:
                if source is not None:
                    raise ConflictError("工作流名称已被其他工作流使用，请填写不同名称。")
                selected = self.read(existing["id"])
                if any(selected[key] != record[key] for key in CONTENT_FIELDS):
                    raise ConflictError("工作流名称已存在且内容不同，请为修改后的工作流填写新名称。")
                record = selected
            elif source is not None:
                if source["name"] == record["name"] and all(source[key] == record[key] for key in CONTENT_FIELDS):
                    record = source
                else:
                    previous = self._path(source_id).read_bytes()
                    self._backup(source_id, previous)
                    record = self._write(record, replace=True)
            else:
                record = self._write(record)
            applied = dict(backend, workflow_id=record["id"], workflow_name=record["name"],
                           workflow_revision=record["revision"])
            try:
                return save_backend(applied)
            except BaseException:
                if created:
                    self._path(record["id"]).unlink()
                elif previous is not None:
                    self._write_raw(record["id"], previous, replace=True)
                raise

    def delete(self, identifier, revision, detach_backends):
        """Archive a template and detach current backend references.

        Current backends and old jobs retain their actual workflow snapshots;
        only the live library association is removed from current backends.
        """
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
            raise ValidationError("删除工作流需要有效的 revision 修订号。")
        with self._writing():
            record = self.read(identifier)
            if record is None:
                raise NotFoundError("工作流已不存在。")
            if record["revision"] != revision:
                raise ConflictError("工作流已变化，请重新载入后删除。")
            raw = self._path(identifier).read_bytes()
            self._backup(identifier, raw)
            self._path(identifier).unlink()
            try:
                detached = detach_backends(identifier)
            except BaseException:
                self._write_raw(identifier, raw, replace=True)
                raise
            return {"deleted": True, "id": identifier, "detached_backends": detached}

    def _backup(self, identifier, raw):
        self._path(identifier)
        directory = self.directory / ".backups"
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.resolve().is_relative_to(self.directory):
            raise ValidationError("工作流备份必须位于工作流目录。")
        path = directory / f"{identifier}-{hashlib.sha256(raw).hexdigest()}.json"
        self._atomic_write(path, raw)

    @contextmanager
    def _writing(self):
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            lock = self.directory / ".write.lock"
            try:
                descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as exc:
                raise ConflictError("工作流库正在保存，请稍后重试。") from exc
            try:
                os.close(descriptor)
                yield
            finally:
                lock.unlink()

    def _write(self, record, replace=False):
        try:
            raw = (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        except (ValueError, TypeError, RecursionError) as exc:
            raise ValidationError("工作流须包含有限的 JSON 值。") from exc
        if len(raw) > MAX_BYTES:
            raise ValidationError("工作流模板超过 8 MB。")
        self._write_raw(record["id"], raw, replace=replace)
        return dict(record, revision=hashlib.sha256(raw).hexdigest())

    def _write_raw(self, identifier, raw, replace=False):
        path = self._path(identifier)
        if path.exists() and not replace:
            raise ConflictError("工作流 ID 已存在，请重试保存。")
        self._atomic_write(path, raw)

    @staticmethod
    def _atomic_write(path, raw):
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix=".workflow-", suffix=".tmp", dir=path.parent)
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
