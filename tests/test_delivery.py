from datetime import UTC, datetime

import httpx

from wall_harness.delivery import deliver_edition
from wall_harness.models import DeliverySpec, Item, RankedItem, WallEdition


def edition() -> WallEdition:
    item = Item.create(
        title="A useful systems paper",
        url="https://example.com/paper",
        summary="New consensus results.",
        source="Research",
    )
    return WallEdition(
        wall_name="systems",
        goal="Learn distributed systems",
        generated_at=datetime.now(UTC),
        items=[RankedItem(item=item, score=0.9, reasons=["matches consensus"], novelty=1)],
        discovered_count=1,
        clustered_count=1,
    )


def test_webhook_delivery_posts_the_edition(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured = {}

    def fake_post(url, **options):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured.update(options)
        return httpx.Response(202, request=httpx.Request("POST", str(url)))

    monkeypatch.setattr("wall_harness.delivery.httpx.post", fake_post)
    delivery = DeliverySpec(targets=[{"type": "webhook", "url": "https://hooks.example.com/wall"}])
    receipts = deliver_edition(edition(), delivery)
    assert captured["timeout"] == 20
    assert captured["json"]["wall_name"] == "systems"
    assert receipts[0].status == "sent"


def test_email_delivery_uses_smtp_without_embedding_secrets(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    events = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):  # type: ignore[no-untyped-def]
            events.append(("connect", host, port, timeout))

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *args):  # type: ignore[no-untyped-def]
            return None

        def starttls(self):  # type: ignore[no-untyped-def]
            events.append(("tls",))

        def login(self, username, password):  # type: ignore[no-untyped-def]
            events.append(("login", username, password))

        def send_message(self, message):  # type: ignore[no-untyped-def]
            events.append(("send", message["To"], message["Subject"]))

    monkeypatch.setattr("wall_harness.delivery.smtplib.SMTP", FakeSMTP)
    monkeypatch.setenv("WALL_SMTP_USER", "reader")
    monkeypatch.setenv("WALL_SMTP_PASSWORD", "secret")
    delivery = DeliverySpec(
        targets=[
            {
                "type": "email",
                "to": "reader@example.com",
                "from_address": "wall@example.com",
                "smtp_host": "smtp.example.com",
                "username_env": "WALL_SMTP_USER",
                "password_env": "WALL_SMTP_PASSWORD",
            }
        ]
    )
    receipts = deliver_edition(edition(), delivery)
    assert ("login", "reader", "secret") in events
    assert ("send", "reader@example.com", "Wall · systems · 1 item") in events
    assert receipts[0].status == "sent"


def test_delivery_failure_is_a_receipt_not_a_lost_edition(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("wall_harness.delivery.httpx.post", fail)
    delivery = DeliverySpec(targets=[{"type": "webhook", "url": "https://hooks.example.com/wall"}])
    receipts = deliver_edition(edition(), delivery)
    assert receipts[0].status == "failed"
    assert "offline" in (receipts[0].detail or "")
