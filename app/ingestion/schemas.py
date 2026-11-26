import hashlib
import re
from html import unescape
from pydantic import BaseModel, field_validator


def normalize_html(raw_html: str) -> str:
    text = unescape(raw_html or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class NormalizedJob(BaseModel):
    external_id: str
    source: str
    title: str
    location: str
    is_remote: bool
    description: str
    apply_url: str

    @field_validator("description", mode="before")
    @classmethod
    def _clean_description(cls, value: str) -> str:
        return normalize_html(value or "")

    @property
    def content_hash(self) -> str:
        payload = (
            f"{self.title.lower().strip()}|"
            f"{self.location.lower().strip()}|"
            f"{self.description.lower().strip()}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
