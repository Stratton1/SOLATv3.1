"""
Disk failure simulators for chaos testing.

Provides fixtures for simulating disk-related failures:
- Disk full (ENOSPC)
- Partial writes (write succeeds, flush fails)
- Directory disappearing mid-operation
"""

import errno
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, mock_open, patch


class DiskChaos:
    """Disk failure simulation helpers."""

    @staticmethod
    def disk_full_on_write(bytes_before_full: int = 100):
        """
        Context manager that simulates disk full after N bytes written.

        Args:
            bytes_before_full: Number of bytes to write before raising ENOSPC

        Usage:
            with DiskChaos.disk_full_on_write(100):
                # Operations will fail after 100 bytes written
                file.write(data)
        """

        class DiskFullMock:
            """Mock file handle that raises ENOSPC after N bytes."""

            def __init__(self, *args: Any, **kwargs: Any):
                self._bytes_written = 0
                self._threshold = bytes_before_full
                self._closed = False

            def write(self, data: Any) -> int:
                """Write data, raising ENOSPC if threshold exceeded."""
                if isinstance(data, (str, bytes)):
                    size = len(data)
                else:
                    size = len(str(data))

                if self._bytes_written + size > self._threshold:
                    raise OSError(errno.ENOSPC, "No space left on device")

                self._bytes_written += size
                return size

            def close(self) -> None:
                """Close file handle."""
                self._closed = True

            def flush(self) -> None:
                """Flush buffer."""
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args: Any):
                self.close()

        return patch("builtins.open", side_effect=DiskFullMock)

    @staticmethod
    def partial_write_on_flush():
        """
        Context manager that simulates write success but flush failure.

        Simulates scenario where data written to buffer but flush to disk fails.

        Usage:
            with DiskChaos.partial_write_on_flush():
                file.write(data)  # Succeeds
                file.flush()      # Raises OSError(EIO)
        """

        class PartialWriteMock:
            """Mock file handle where flush fails."""

            def __init__(self, *args: Any, **kwargs: Any):
                self._buffer = []
                self._closed = False

            def write(self, data: Any) -> int:
                """Write succeeds, stores in buffer."""
                self._buffer.append(data)
                if isinstance(data, (str, bytes)):
                    return len(data)
                return len(str(data))

            def flush(self) -> None:
                """Flush raises I/O error."""
                raise OSError(errno.EIO, "Input/output error on flush")

            def close(self) -> None:
                """Close without flushing."""
                self._closed = True

            def __enter__(self):
                return self

            def __exit__(self, *args: Any):
                self.close()

        return patch("builtins.open", side_effect=PartialWriteMock)

    @staticmethod
    def directory_disappears(target_dir: Path):
        """
        Context manager that makes a directory appear to vanish.

        Args:
            target_dir: Path to simulate disappearance

        Usage:
            with DiskChaos.directory_disappears(Path("/data")):
                # Operations on /data will raise FileNotFoundError
                (target_dir / "file.txt").write_text("data")
        """

        def mock_exists(path: Any) -> bool:
            """Mock Path.exists() to return False for target."""
            path_obj = Path(path) if not isinstance(path, Path) else path
            if target_dir in path_obj.parents or path_obj == target_dir:
                return False
            return True

        def mock_mkdir(*args: Any, **kwargs: Any) -> None:
            """Mock mkdir to raise FileNotFoundError."""
            raise FileNotFoundError(errno.ENOENT, "Parent directory does not exist")

        return patch.multiple(
            "pathlib.Path",
            exists=MagicMock(side_effect=mock_exists),
            mkdir=MagicMock(side_effect=mock_mkdir),
        )

    @staticmethod
    def corrupt_file_content(file_path: Path, corrupt_at_byte: int):
        """
        Context manager that corrupts file content at specific byte offset.

        Args:
            file_path: Path to file to corrupt
            corrupt_at_byte: Byte offset where corruption occurs

        Usage:
            with DiskChaos.corrupt_file_content(Path("ledger.jsonl"), 500):
                # Read operations will see corruption at byte 500
                content = file_path.read_text()
        """

        original_open = open

        def corrupted_open(path: Any, *args: Any, **kwargs: Any):
            """Open file, corrupt content if reading target file."""
            file_obj = original_open(path, *args, **kwargs)

            if Path(path) == file_path and "r" in kwargs.get("mode", args[0] if args else "r"):

                class CorruptedReader:
                    """Reader that injects corruption."""

                    def __init__(self, inner):
                        self._inner = inner
                        self._pos = 0

                    def read(self, size: int = -1):
                        """Read with corruption injection."""
                        data = self._inner.read(size)
                        if self._pos <= corrupt_at_byte < self._pos + len(data):
                            offset = corrupt_at_byte - self._pos
                            data = data[:offset] + "\x00\xff\x00" + data[offset + 3 :]
                        self._pos += len(data)
                        return data

                    def __getattr__(self, name: str):
                        return getattr(self._inner, name)

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return self._inner.__exit__(*args)

                return CorruptedReader(file_obj)

            return file_obj

        return patch("builtins.open", side_effect=corrupted_open)
