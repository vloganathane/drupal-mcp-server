"""Bearer token authentication for Drupal."""
from typing import Dict


class TokenAuth:
    def __init__(self, token: str):
        self._token = token

    def get_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}
