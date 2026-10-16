"""Small persistent retention policy; changes are explicit and locally atomic."""
import json
import logging
import threading

from .assets import atomic_write
from ..domain import ValidationError

DEFAULT_RETENTION_DAYS = 1
LOG = logging.getLogger(__name__)


def retention_days(value):
    if type(value) is not int or not 0 <= value <= 3650:
        raise ValidationError("保留天数须为 0–3650 之间的整数，0 表示关闭自动清理。")
    return value


class HistorySettings:
    def __init__(self, paths):
        self.paths = paths
        self.path = paths.root / "history-cleanup.json"
        self.lock = threading.Lock()

    def get(self):
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(4097)
        except FileNotFoundError:
            return {"unliked_retention_days":DEFAULT_RETENTION_DAYS}
        if len(raw) > 4096:
            raise ValidationError("历史图片清理设置过大，请重新保存设置。")
        try:
            data = json.loads(raw.decode("utf-8-sig"))
            if not isinstance(data,dict):
                raise ValueError()
            days = retention_days(data["unliked_retention_days"])
        except (ValueError,UnicodeError,KeyError):
            raise ValidationError("历史图片清理设置无效；自动过期清理已暂停，请重新保存设置。") from None
        return {"unliked_retention_days":days}

    def retention(self):
        try:
            return self.get()["unliked_retention_days"]
        except (ValidationError,OSError):
            LOG.warning("Invalid history cleanup settings; expiration is disabled until repaired")
            return 0

    def save(self, days):
        document = {"unliked_retention_days":retention_days(days)}
        raw = (json.dumps(document,indent=2)+"\n").encode("utf-8")
        with self.lock:
            atomic_write(self.path,raw,self.paths.tmp)
        return document
