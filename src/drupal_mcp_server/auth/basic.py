"""Basic authentication for Drupal."""
import base64


class BasicAuth:
    def __init__(self, username: str, password: str):
        self._token = base64.b64encode(f"{username}:{password}".encode()).decode()

    def get_headers(self) -> dict[str, str]:
        return {"Authorization": f"Basic {self._token}"}
