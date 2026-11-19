"""Your topic queue. Topics only enter production after YOU pick them in Telegram and send your own input.

Item lifecycle: proposed → (you tap "Make this") awaiting_input → (you send text or a voice note) ready
→ produced.  Or: proposed/awaiting_input → dropped (you tap "Skip"/"Drop").
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone

ACTIVE = ("proposed", "awaiting_input", "ready")


@dataclass
class Item:
    id: str
    key: str
    topic: str
    category: str
    card: dict
    status: str = "proposed"
    format: str = ""
    proposed_on: str = ""
    picked_at: str = ""
    creator_input: str = ""
    input_kind: str = ""          # text | voice
    input_msg_id: int | None = None
    proposal_msg_id: int | None = None
    produced_on: str = ""
    jobs: list = field(default_factory=list)
    auto: bool = False            # picked automatically by research (TOPIC_MODE=auto)
    why: list = field(default_factory=list)  # why it was picked, with source URLs


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TopicQueue:
    KEY = "topic_queue"

    def __init__(self, store):
        self.store = store

    def items(self) -> list[Item]:
        return [Item(**d) for d in json.loads(self.store.kv_get(self.KEY, "[]"))]

    def _save(self, items: list[Item]) -> None:
        keep = [i for i in items if i.status in ACTIVE] + [i for i in items if i.status not in ACTIVE][-200:]
        self.store.kv_set(self.KEY, json.dumps([asdict(i) for i in keep]))

    def get(self, item_id: str) -> Item | None:
        return next((i for i in self.items() if i.id == item_id), None)

    def update(self, item_id: str, **changes) -> Item:
        items = self.items()
        for it in items:
            if it.id == item_id:
                for k, v in changes.items():
                    setattr(it, k, v)
                self._save(items)
                return it
        raise KeyError(item_id)

    def add_proposals(self, cards: list[dict], day: date) -> list[Item]:
        items = self.items()
        active_keys = {i.key for i in items if i.status in ACTIVE}
        new = []
        for c in cards:
            if c["key"] in active_keys:
                continue
            iid = "t" + hashlib.sha1(f"{c['key']}{day}".encode()).hexdigest()[:6]
            new.append(Item(iid, c["key"], c["topic"], c.get("category", ""), c, proposed_on=day.isoformat()))
        self._save(items + new)
        return new

    def pick(self, item_id: str, fmt: str) -> Item:
        return self.update(item_id, status="awaiting_input", format=fmt, picked_at=_now())

    def add_input(self, item_id: str, text: str, kind: str = "text") -> Item:
        it = self.get(item_id)
        joined = (it.creator_input + "\n" + text).strip() if it.creator_input else text.strip()
        return self.update(item_id, creator_input=joined, input_kind=kind if not it.input_kind else it.input_kind,
                           status="ready")

    def awaiting_input(self) -> list[Item]:
        return [i for i in self.items() if i.status == "awaiting_input"]

    def ready(self) -> list[Item]:
        return sorted((i for i in self.items() if i.status == "ready"), key=lambda i: i.picked_at)

    def by_message(self, message_id: int) -> Item | None:
        return next((i for i in self.items() if message_id in (i.input_msg_id, i.proposal_msg_id)), None)

    def status_text(self) -> str:
        groups = {"ready": "✅ Ready (has your input)", "awaiting_input": "✍️ Waiting for your input",
                  "proposed": "💡 Ideas you haven't picked yet"}
        lines = ["YOUR TOPIC QUEUE"]
        for st, title in groups.items():
            its = [i for i in self.items() if i.status == st]
            if its:
                lines.append(f"\n{title}:")
                lines += [f"• {i.topic} ({i.format or 'format chosen when picked'}) [{i.id}]" for i in its]
        return "\n".join(lines) if len(lines) > 1 else "Your queue is empty. New ideas arrive every Sunday."


__all__ = ["TopicQueue", "Item", "ACTIVE"]
