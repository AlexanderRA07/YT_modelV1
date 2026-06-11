import json
import uuid
from datetime import datetime
from pathlib import Path


class DraftStore:
    """
    Manages a per-channel drafts.json file for partially-written topic entries.
    Drafts are converted to CSV rows by TopicStore.add_topic() on submit.
    """

    FIELDS = ("name", "niche", "description", "format", "references", "concepts")

    def __init__(self, json_path: str):
        self.path = Path(json_path)
        self._ensure_file()

    def _ensure_file(self):
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("[]", encoding="utf-8")

    def _read(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, drafts: list[dict]):
        self.path.write_text(
            json.dumps(drafts, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def get_all(self) -> list[dict]:
        return self._read()

    def get_by_id(self, draft_id: str) -> dict | None:
        return next((d for d in self._read() if d["draft_id"] == draft_id), None)

    def create(self, **fields) -> dict:
        drafts = self._read()
        now = datetime.now().strftime("%Y-%m-%d")
        draft = {
            "draft_id":    str(uuid.uuid4())[:8],
            "name":        fields.get("name", ""),
            "niche":       fields.get("niche", ""),
            "description": fields.get("description", ""),
            "format":      fields.get("format", ""),
            "references":  fields.get("references", ""),
            "concepts":    fields.get("concepts", ""),
            "created_at":  now,
            "updated_at":  now,
        }
        drafts.append(draft)
        self._write(drafts)
        return draft

    def update(self, draft_id: str, **fields) -> dict | None:
        drafts = self._read()
        for d in drafts:
            if d["draft_id"] == draft_id:
                for k, v in fields.items():
                    if k in self.FIELDS:
                        d[k] = v
                d["updated_at"] = datetime.now().strftime("%Y-%m-%d")
                self._write(drafts)
                return d
        return None

    def delete(self, draft_id: str) -> bool:
        drafts = self._read()
        filtered = [d for d in drafts if d["draft_id"] != draft_id]
        if len(filtered) == len(drafts):
            return False
        self._write(filtered)
        return True
