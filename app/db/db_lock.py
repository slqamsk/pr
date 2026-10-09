"""Механизм блокировки для одного экземпляра приложения.
Windows-only: использует msvcrt.locking на байт 0 lock-файла.

Файлы блокировок лежат в data/ и не содержат значимых данных —
важна только OS-блокировка, которая снимается автоматически
при завершении процесса, включая аварийное.

    pr_v01.main.lock    — держит pr_v01.pyw
    pr_v01.stat.lock    — держит pr_v01_stat.pyw
    pr_v01.export.lock  — держит pr_v01_export_import.pyw
"""
import os
from pathlib import Path
import msvcrt

from . import db_init

MAIN_LOCK_PATH   = db_init.DATA_DIR / "pr_v01.main.lock"
STAT_LOCK_PATH   = db_init.DATA_DIR / "pr_v01.stat.lock"
EXPORT_LOCK_PATH = db_init.DATA_DIR / "pr_v01.export.lock"


class Lock:
    """Эксклюзивная блокировка одного файла на время жизни процесса."""

    def __init__(self, path):
        self.path = Path(path)
        self._fh = None

    def acquire(self) -> bool:
        """Пытается взять блокировку. True — получилось, False — занято."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR | os.O_BINARY)
        except OSError:
            return False

        try:
            fh = os.fdopen(fd, "r+b")
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            return False

        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            try:
                fh.close()
            except Exception:
                pass
            return False

        # Записываем PID — чисто информативно, для отладки.
        try:
            fh.seek(0)
            fh.write(f"{os.getpid()}    ".encode("ascii"))
            fh.flush()
        except Exception:
            pass

        self._fh = fh
        return True

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            self._fh.seek(0)
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        try:
            self._fh.close()
        except Exception:
            pass
        self._fh = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_):
        self.release()


def is_free(path) -> bool:
    """Свободен ли lock-файл. Не оставляет за собой блокировок.
    Если файла нет — считаем свободным. Если файл открыть не удалось —
    считаем занятым, чтобы не запустить второе приложение поверх."""
    p = Path(path)
    if not p.is_file():
        return True

    try:
        fd = os.open(str(p), os.O_RDWR | os.O_BINARY)
    except OSError:
        return False

    try:
        fh = os.fdopen(fd, "r+b")
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        return False

    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        try:
            fh.close()
        except Exception:
            pass
        return False

    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    try:
        fh.close()
    except Exception:
        pass
    return True