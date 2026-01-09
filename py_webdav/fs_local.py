"""Local filesystem implementation for WebDAV."""

from __future__ import annotations

import mimetypes
import os
import shutil
from datetime import UTC, datetime
from hashlib import md5
from pathlib import Path
from typing import BinaryIO

from .internal import HTTPError
from .webdav import (
    ConditionalMatch,
    CopyOptions,
    CreateOptions,
    FileInfo,
    MoveOptions,
    RemoveAllOptions,
)


class LocalFileSystem:
    """Local filesystem backend for WebDAV server."""

    def __init__(self, root_dir: str | Path):
        """Initialize local filesystem.

        Args:
            root_dir: Root directory for the filesystem
        """
        self.root_dir = Path(root_dir).resolve()
        if not self.root_dir.exists():
            raise ValueError(f"Root directory does not exist: {root_dir}")
        if not self.root_dir.is_dir():
            raise ValueError(f"Root path is not a directory: {root_dir}")

    def _local_path(self, name: str) -> Path:
        """Convert WebDAV path to local filesystem path.

        Args:
            name: WebDAV path (must be absolute)

        Returns:
            Local filesystem path

        Raises:
            HTTPError: If path is invalid
        """
        if "\x00" in name:
            raise HTTPError(400, Exception("webdav: invalid character in path"))

        # Normalize path
        name = name.strip()
        if not name.startswith("/"):
            raise HTTPError(400, Exception(f"webdav: expected absolute path, got {name!r}"))

        # Remove leading slash and resolve relative to root
        rel_path = name.lstrip("/")
        local_path = (self.root_dir / rel_path).resolve()

        # Security check: ensure path is within root_dir
        try:
            local_path.relative_to(self.root_dir)
        except ValueError as e:
            raise HTTPError(403, Exception("webdav: path outside root directory")) from e

        return local_path

    def _external_path(self, local_path: Path) -> str:
        """Convert local filesystem path to WebDAV path.

        Args:
            local_path: Local filesystem path

        Returns:
            WebDAV path (absolute)
        """
        rel_path = local_path.relative_to(self.root_dir)
        return "/" + str(rel_path).replace(os.sep, "/")

    async def open(self, name: str) -> BinaryIO:
        """Open a file for reading.

        Args:
            name: File path

        Returns:
            Binary file object
        """
        path = self._local_path(name)
        try:
            return open(path, "rb")
        except FileNotFoundError as e:
            raise HTTPError(404, e) from e
        except PermissionError as e:
            raise HTTPError(403, e) from e
        except Exception as e:
            raise HTTPError(500, e) from e

    def _file_info_from_stat(self, path: Path, webdav_path: str) -> FileInfo:
        """Create FileInfo from os.stat result.

        Args:
            path: Local filesystem path
            webdav_path: WebDAV path

        Returns:
            FileInfo object
        """
        stat = path.stat()

        # Get MIME type
        mime_type = ""
        if not path.is_dir():
            mime_type, _ = mimetypes.guess_type(str(path))
            mime_type = mime_type or "application/octet-stream"

        # Create ETag - use content hash for CalDAV/CardDAV files to match backend behavior
        if not path.is_dir() and (path.suffix == ".vcf" or path.suffix == ".ics"):
            # Use MD5 of content for .vcf and .ics files (matches CardDAV/CalDAV backends)
            content = path.read_bytes()
            etag = md5(content).hexdigest()
        else:
            # Use mtime + size for other files
            etag = f"{stat.st_mtime_ns:x}{stat.st_size:x}"

        return FileInfo(
            path=webdav_path,
            size=stat.st_size if not path.is_dir() else 0,
            mod_time=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            is_dir=path.is_dir(),
            mime_type=mime_type,
            etag=etag,
        )

    async def stat(self, name: str) -> FileInfo:
        """Get file information.

        Args:
            name: File path

        Returns:
            FileInfo object
        """
        path = self._local_path(name)
        try:
            return self._file_info_from_stat(path, name)
        except FileNotFoundError as e:
            raise HTTPError(404, e) from e
        except PermissionError as e:
            raise HTTPError(403, e) from e
        except Exception as e:
            raise HTTPError(500, e) from e

    async def read_dir(self, name: str, recursive: bool = False) -> list[FileInfo]:
        """List directory contents.

        Args:
            name: Directory path
            recursive: Whether to list recursively

        Returns:
            List of FileInfo objects
        """
        path = self._local_path(name)

        if not path.is_dir():
            raise HTTPError(400, Exception("webdav: path is not a directory"))

        files: list[FileInfo] = []

        try:
            if recursive:
                # Walk directory recursively
                for root, _dirs, filenames in os.walk(path):
                    root_path = Path(root)

                    # Add directory itself
                    webdav_path = self._external_path(root_path)
                    files.append(self._file_info_from_stat(root_path, webdav_path))

                    # Add files
                    for filename in filenames:
                        file_path = root_path / filename
                        try:
                            webdav_path = self._external_path(file_path)
                            files.append(self._file_info_from_stat(file_path, webdav_path))
                        except (PermissionError, OSError):
                            # Skip files we can't access
                            continue
            else:
                # List immediate children only
                # Add the directory itself
                files.append(self._file_info_from_stat(path, name))

                # Add children
                for item in path.iterdir():
                    try:
                        webdav_path = self._external_path(item)
                        files.append(self._file_info_from_stat(item, webdav_path))
                    except (PermissionError, OSError):
                        # Skip files we can't access
                        continue

        except PermissionError as e:
            raise HTTPError(403, e) from e
        except Exception as e:
            raise HTTPError(500, e) from e

        return files

    def _check_conditional_matches(
        self,
        fi: FileInfo | None,
        if_match: ConditionalMatch | None,
        if_none_match: ConditionalMatch | None,
    ) -> None:
        """Check If-Match and If-None-Match conditions.

        Args:
            fi: FileInfo or None if file doesn't exist
            if_match: If-Match condition
            if_none_match: If-None-Match condition

        Raises:
            HTTPError: If conditions are not met
        """
        etag = fi.etag if fi else ""

        if if_match and if_match.is_set():
            if not if_match.match_etag(etag):
                raise HTTPError(412, Exception("If-Match condition failed"))

        if if_none_match and if_none_match.is_set():
            if if_none_match.match_etag(etag):
                raise HTTPError(412, Exception("If-None-Match condition failed"))

    async def create(
        self, name: str, body: BinaryIO, opts: CreateOptions | None = None
    ) -> tuple[FileInfo, bool]:
        """Create or update a file.

        Args:
            name: File path
            body: File content
            opts: Create options

        Returns:
            Tuple of (file_info, created) where created is True if file was created
        """
        path = self._local_path(name)

        # Check if file exists
        fi = None
        created = False
        try:
            fi = await self.stat(name)
        except HTTPError as e:
            if e.code == 404:
                created = True
            else:
                raise

        # Check conditional matches
        if opts:
            self._check_conditional_matches(fi, opts.if_match, opts.if_none_match)

        # Write file
        try:
            # Ensure parent directory exists
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "wb") as f:
                # Copy content
                while chunk := body.read(8192):
                    f.write(chunk)

            # Get new file info
            fi = await self.stat(name)
            return fi, created

        except PermissionError as e:
            raise HTTPError(403, e) from e
        except Exception as e:
            # Clean up on error
            if path.exists():
                path.unlink()
            raise HTTPError(500, e) from e

    async def remove_all(self, name: str, opts: RemoveAllOptions | None = None) -> None:
        """Remove a file or directory recursively.

        Args:
            name: Path to remove
            opts: Remove options
        """
        path = self._local_path(name)

        # WebDAV requires 404 if resource doesn't exist
        fi = await self.stat(name)

        # Check conditional matches
        if opts:
            self._check_conditional_matches(fi, opts.if_match, opts.if_none_match)

        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except FileNotFoundError as e:
            raise HTTPError(404, e) from e
        except PermissionError as e:
            raise HTTPError(403, e) from e
        except Exception as e:
            raise HTTPError(500, e) from e

    async def mkdir(self, name: str) -> None:
        """Create a directory.

        Args:
            name: Directory path
        """
        path = self._local_path(name)

        try:
            path.mkdir(parents=False)
        except FileExistsError as e:
            raise HTTPError(405, e) from e  # Method Not Allowed
        except FileNotFoundError as e:
            raise HTTPError(409, e) from e  # Conflict (parent doesn't exist)
        except PermissionError as e:
            raise HTTPError(403, e) from e
        except Exception as e:
            raise HTTPError(500, e) from e

    def _copy_file(self, src: Path, dst: Path) -> None:
        """Copy a regular file.

        Args:
            src: Source path
            dst: Destination path
        """
        # Create parent directory if needed
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(src, dst)

    async def copy(self, name: str, dest: str, options: CopyOptions | None = None) -> bool:
        """Copy a file or directory.

        Args:
            name: Source path
            dest: Destination path
            options: Copy options

        Returns:
            True if destination was created, False if it was overwritten
        """
        if options is None:
            options = CopyOptions()

        src_path = self._local_path(name)
        dst_path = self._local_path(dest)

        # Check if source exists
        if not src_path.exists():
            raise HTTPError(404, Exception("source not found"))

        # Check if destination exists
        created = not dst_path.exists()

        if dst_path.exists():
            if options.no_overwrite:
                raise FileExistsError("destination already exists")
            # Remove existing destination
            if dst_path.is_dir():
                shutil.rmtree(dst_path)
            else:
                dst_path.unlink()

        try:
            if src_path.is_dir():
                if options.no_recursive:
                    # Copy only the directory, not contents
                    dst_path.mkdir(parents=False)
                else:
                    # Copy recursively
                    shutil.copytree(src_path, dst_path)
            else:
                # Copy file
                self._copy_file(src_path, dst_path)

            return created

        except FileNotFoundError as e:
            raise HTTPError(409, e) from e  # Conflict
        except PermissionError as e:
            raise HTTPError(403, e) from e
        except Exception as e:
            raise HTTPError(500, e) from e

    async def move(self, name: str, dest: str, options: MoveOptions | None = None) -> bool:
        """Move a file or directory.

        Args:
            name: Source path
            dest: Destination path
            options: Move options

        Returns:
            True if destination was created, False if it was overwritten
        """
        if options is None:
            options = MoveOptions()

        src_path = self._local_path(name)
        dst_path = self._local_path(dest)

        # Check if source exists
        if not src_path.exists():
            raise HTTPError(404, Exception("source not found"))

        # Check if destination exists
        created = not dst_path.exists()

        if dst_path.exists():
            if options.no_overwrite:
                raise FileExistsError("destination already exists")
            # Remove existing destination
            if dst_path.is_dir():
                shutil.rmtree(dst_path)
            else:
                dst_path.unlink()

        try:
            # Ensure parent directory exists
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            # Move/rename
            shutil.move(str(src_path), str(dst_path))

            return created

        except FileNotFoundError as e:
            raise HTTPError(409, e) from e  # Conflict
        except PermissionError as e:
            raise HTTPError(403, e) from e
        except Exception as e:
            raise HTTPError(500, e) from e
