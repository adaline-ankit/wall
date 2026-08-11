from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

import httpx

from .models import DeliveryReceipt, DeliverySpec, DeliveryTarget, WallEdition
from .renderers import render_markdown


def deliver_edition(edition: WallEdition, delivery: DeliverySpec) -> list[DeliveryReceipt]:
    receipts: list[DeliveryReceipt] = []
    for target in delivery.targets:
        try:
            if target.type == "webhook":
                send_webhook(edition, target)
            else:
                send_email(edition, target)
            receipts.append(DeliveryReceipt(target=target.type, status="sent"))
        except Exception as exc:
            receipts.append(DeliveryReceipt(target=target.type, status="failed", detail=str(exc)))
    return receipts


def send_webhook(edition: WallEdition, target: DeliveryTarget) -> None:
    if target.url is None:
        raise ValueError("webhook URL is missing")
    response = httpx.post(str(target.url), json=edition.model_dump(mode="json"), timeout=20)
    response.raise_for_status()


def send_email(edition: WallEdition, target: DeliveryTarget) -> None:
    if not target.smtp_host or not target.to or not target.from_address:
        raise ValueError("email target is incomplete")
    message = EmailMessage()
    message["Subject"] = (
        f"Wall · {edition.wall_name} · {len(edition.items)} "
        f"{'item' if len(edition.items) == 1 else 'items'}"
    )
    message["From"] = target.from_address
    message["To"] = target.to
    message.set_content(render_markdown(edition))

    with smtplib.SMTP(target.smtp_host, target.smtp_port, timeout=20) as client:
        if target.starttls:
            client.starttls()
        if target.username_env or target.password_env:
            if not target.username_env or not target.password_env:
                raise ValueError("email auth requires both username_env and password_env")
            username = os.getenv(target.username_env)
            password = os.getenv(target.password_env)
            if not username or not password:
                raise RuntimeError(
                    f"Set {target.username_env} and {target.password_env} for email delivery"
                )
            client.login(username, password)
        client.send_message(message)
