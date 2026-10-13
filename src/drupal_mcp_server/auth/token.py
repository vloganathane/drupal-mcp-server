"""Bearer token authentication for Drupal."""


class TokenAuth:
    def __init__(self, token: str):
        self._token = token

    def get_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}
