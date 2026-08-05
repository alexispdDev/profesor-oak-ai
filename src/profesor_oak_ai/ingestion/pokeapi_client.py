import time

import requests

BASE_URL = "https://pokeapi.co/api/v2"
REQUEST_DELAY_SECONDS = 0.2
MAX_RETRIES = 3


class PokeApiClient:
    def __init__(self, base_url: str = BASE_URL) -> None:
        self.base_url = base_url
        self.session = requests.Session()

    def get(self, url_or_path: str) -> dict:
        url = url_or_path if url_or_path.startswith("http") else f"{self.base_url}/{url_or_path}"

        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                time.sleep(REQUEST_DELAY_SECONDS)
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(REQUEST_DELAY_SECONDS * attempt)

        raise RuntimeError(f"Failed to GET {url} after {MAX_RETRIES} attempts") from last_error
