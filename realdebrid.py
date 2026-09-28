import requests


class RealDebrid:
    def __init__(self, token):
        self.base_url = "https://api.real-debrid.com/rest/1.0"

        self.headers = {
            "Authorization": f"Bearer {token}"
        }

    def get_torrents(self):
        """Get all torrents from the Real-Debrid account."""

        page = 1
        all_torrents = []

        while True:
            response = requests.get(
                f"{self.base_url}/torrents",
                headers=self.headers,
                params={
                    "page": page,
                    "limit": 100
                }
            )

            response.raise_for_status()

            torrents = response.json()

            if not torrents:
                break

            all_torrents.extend(torrents)

            if len(torrents) < 100:
                break

            page += 1

        return all_torrents

    def get_torrent_info(self, torrent_id):
        """Get detailed information about a torrent."""

        response = requests.get(
            f"{self.base_url}/torrents/info/{torrent_id}",
            headers=self.headers
        )

        response.raise_for_status()

        return response.json()

    def select_files(self, torrent_id, file_ids):
        """Select files from a torrent."""

        response = requests.post(
            f"{self.base_url}/torrents/selectFiles/{torrent_id}",
            headers=self.headers,
            data={
                "files": ",".join(str(file_id) for file_id in file_ids)
            }
        )

        response.raise_for_status()

    def unrestrict_link(self, link):
        """Turn a Real-Debrid link into a direct download URL."""

        response = requests.post(
            f"{self.base_url}/unrestrict/link",
            headers=self.headers,
            data={
                "link": link
            }
        )

        response.raise_for_status()

        return response.json()
