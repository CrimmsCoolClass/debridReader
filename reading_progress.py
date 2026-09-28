import json
from pathlib import Path


class ReadingProgress:
    """
    Persistent reading progress for Debrid Reader.

    This stores only small metadata.
    It does not cache book data or page images.
    """

    def __init__(self):
        self.path = (
            Path.home()
            / ".cache"
            / "debrid-reader"
            / "reading-progress.json"
        )

        self.data = {
            "last_read": None,
            "volumes": {},
        }

        self._load()

    def _load(self):
        try:
            with self.path.open(
                "r",
                encoding="utf-8",
            ) as file:
                loaded = json.load(file)

            if isinstance(loaded, dict):
                self.data.update(loaded)

            if not isinstance(
                self.data.get("volumes"),
                dict,
            ):
                self.data["volumes"] = {}

        except (
            FileNotFoundError,
            json.JSONDecodeError,
            OSError,
        ):
            self.data = {
                "last_read": None,
                "volumes": {},
            }

    def _save(self):
        try:
            self.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            temporary_path = self.path.with_suffix(
                ".tmp"
            )

            with temporary_path.open(
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    self.data,
                    file,
                    indent=2,
                )

            temporary_path.replace(
                self.path
            )

        except OSError:
            # Reading progress should never prevent
            # the reader from working.
            pass

    def get_page(self, key):
        entry = self.data["volumes"].get(key)

        if not isinstance(entry, dict):
            return 0

        page = entry.get(
            "page",
            0,
        )

        try:
            return max(
                0,
                int(page),
            )

        except (
            TypeError,
            ValueError,
        ):
            return 0

    def save_page(
        self,
        key,
        torrent_id,
        volume_name,
        page,
    ):
        page = max(
            0,
            int(page),
        )

        self.data["volumes"][key] = {
            "torrent_id": torrent_id,
            "volume": volume_name,
            "page": page,
        }

        self.data["last_read"] = {
            "key": key,
            "torrent_id": torrent_id,
            "volume": volume_name,
            "page": page,
        }

        self._save()

    def remove_volume(self, key):
        """
        Remove a completed volume from reading progress.
        """

        removed = (
            self.data["volumes"].pop(
                key,
                None,
            )
            is not None
        )

        last_read = self.data.get(
            "last_read"
        )

        if (
            isinstance(last_read, dict)
            and last_read.get("key") == key
        ):
            self.data["last_read"] = None

        if removed:
            self._save()

        return removed

    def get_last_read(self):
        last_read = self.data.get(
            "last_read"
        )

        if isinstance(
            last_read,
            dict,
        ):
            return last_read.copy()

        return None
