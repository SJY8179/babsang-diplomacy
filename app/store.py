import json
import sqlite3
from pathlib import Path

from app.config import settings
from app.events import now_kst
from app.models import Feedback

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meetings (
  id TEXT PRIMARY KEY, group_id TEXT NOT NULL, title TEXT NOT NULL, when_at TEXT, area TEXT, created_at TEXT NOT NULL,
  lead TEXT, team_size INTEGER
);
CREATE TABLE IF NOT EXISTS participants (
  id INTEGER PRIMARY KEY AUTOINCREMENT, meeting_id TEXT NOT NULL, token TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL, role TEXT, origin TEXT, budget INTEGER, diet TEXT, allergy TEXT,
  food TEXT, mood TEXT, done INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS visits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  group_id TEXT NOT NULL, place_id TEXT NOT NULL, place_name TEXT NOT NULL,
  attrs TEXT NOT NULL DEFAULT '[]', visited_at TEXT NOT NULL,
  satisfaction REAL NOT NULL, revisit INTEGER NOT NULL, per_person INTEGER
);
"""


class Store:
    def __init__(self, path: Path | str = settings.db_path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def ensure_group(self, group_id: str, name: str | None = None) -> None:
        self.db.execute("INSERT OR IGNORE INTO groups(id, name) VALUES (?, ?)", (group_id, name or group_id))
        self.db.commit()

    def add_group(self, name: str) -> dict:
        import re, uuid
        gid = re.sub(r"[^0-9a-z]+", "-", name.lower()).strip("-") or uuid.uuid4().hex[:6]
        if self.db.execute("SELECT 1 FROM groups WHERE id=?", (gid,)).fetchone():
            gid = f"{gid}-{uuid.uuid4().hex[:4]}"
        self.db.execute("INSERT INTO groups(id, name) VALUES (?, ?)", (gid, name))
        self.db.commit()
        return {"id": gid, "name": name}

    def groups(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT id, name FROM groups ORDER BY name")]

    def add_visit(self, fb: Feedback, visited_at: str | None = None) -> None:
        self.ensure_group(fb.group_id)
        self.db.execute(
            "INSERT INTO visits(group_id, place_id, place_name, attrs, visited_at, satisfaction, revisit, per_person)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (fb.group_id, fb.place_id, fb.place_name, json.dumps(fb.attrs), visited_at or now_kst().date().isoformat(),
             fb.satisfaction, int(fb.revisit), fb.per_person),
        )
        self.db.commit()

    def visits(self, group_id: str) -> list[dict]:
        rows = self.db.execute("SELECT * FROM visits WHERE group_id=? ORDER BY visited_at DESC, id DESC", (group_id,))
        return [{**dict(r), "attrs": json.loads(r["attrs"]), "revisit": bool(r["revisit"])} for r in rows]

    def clear_group(self, group_id: str) -> None:
        self.db.execute("DELETE FROM visits WHERE group_id=?", (group_id,))
        self.db.commit()

    # ---- 회식(모임 한 번)과 참석자 ----
    def add_meeting(self, group_id: str, title: str, when_at: str | None, area: str | None,
                    lead: str | None = None, team_size: int | None = None) -> dict:
        import uuid
        mid = uuid.uuid4().hex[:8]
        self.ensure_group(group_id)
        self.db.execute("INSERT INTO meetings(id, group_id, title, when_at, area, created_at, lead, team_size) VALUES (?,?,?,?,?,?,?,?)",
                        (mid, group_id, title, when_at, area, now_kst().isoformat(), lead, team_size))
        self.db.commit()
        return self.meeting(mid)

    def meeting(self, mid: str) -> dict | None:
        r = self.db.execute("SELECT * FROM meetings WHERE id=?", (mid,)).fetchone()
        return dict(r) if r else None

    def latest_meeting(self, group_id: str) -> dict | None:
        r = self.db.execute("SELECT * FROM meetings WHERE group_id=? ORDER BY created_at DESC LIMIT 1", (group_id,)).fetchone()
        return dict(r) if r else None

    def update_meeting(self, mid: str, **kw) -> None:
        for k in ("title", "when_at", "area"):
            if k in kw and kw[k] is not None:
                self.db.execute(f"UPDATE meetings SET {k}=? WHERE id=?", (kw[k], mid))
        self.db.commit()

    def add_participant(self, mid: str, name: str, role: str | None = None, **fields) -> dict:
        import secrets
        token = secrets.token_urlsafe(16)
        self.db.execute("INSERT INTO participants(meeting_id, token, name, role) VALUES (?,?,?,?)", (mid, token, name, role))
        self.db.commit()
        if fields:
            self.update_participant(token, **fields)
        return self.participant(token)

    def participant(self, token: str) -> dict | None:
        r = self.db.execute("SELECT * FROM participants WHERE token=?", (token,)).fetchone()
        return dict(r) if r else None

    def participants(self, mid: str) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM participants WHERE meeting_id=? ORDER BY id", (mid,))]

    def set_done(self, token: str, done: bool) -> None:
        self.db.execute("UPDATE participants SET done=? WHERE token=?", (int(done), token))
        self.db.commit()

    def update_participant(self, token: str, **kw) -> dict | None:
        cols = ("origin", "budget", "diet", "allergy", "food", "mood")
        for k in cols:
            if k in kw and kw[k] is not None:
                self.db.execute(f"UPDATE participants SET {k}=? WHERE token=?", (kw[k], token))
        p = self.participant(token)
        if p:
            done = int(bool(p["origin"]) and bool(p["budget"]))
            self.db.execute("UPDATE participants SET done=? WHERE token=?", (done, token))
        self.db.commit()
        return self.participant(token)

    def remove_participant(self, token: str) -> None:
        self.db.execute("DELETE FROM participants WHERE token=?", (token,))
        self.db.commit()
