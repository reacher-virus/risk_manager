"""Self-hosted image CAPTCHA. Single-use, short-lived, answer stored only as an HMAC."""
import base64
import hmac
import io
import random
import secrets as pysecrets
from datetime import timedelta

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from sqlalchemy import delete, select, update

from app.auth import secrets as keys
from app.auth.models import Captcha, new_id
from app.core import config as cfg
from app.core.db import utcnow

ALPHABET = "ACDEFGHJKLMNPRTUVWXYZ234679"      # no look-alikes (0/O, 1/I/L, 5/S, 8/B)


def _random_text(n: int = 5) -> str:
    return "".join(pysecrets.choice(ALPHABET) for _ in range(n))


def _render(text: str) -> bytes:
    rnd = random.SystemRandom()
    w, h = 200, 70
    img = Image.new("RGB", (w, h), (244, 245, 247))
    font = ImageFont.load_default(size=40)
    for i, ch in enumerate(text):
        glyph = Image.new("RGBA", (48, 60), (0, 0, 0, 0))
        ImageDraw.Draw(glyph).text((6, 4), ch, font=font, fill=(rnd.randint(20, 90), rnd.randint(20, 90), rnd.randint(20, 90), 255))
        glyph = glyph.rotate(rnd.uniform(-22, 22), resample=Image.BICUBIC, expand=True)
        img.paste(glyph, (10 + i * 34 + rnd.randint(-3, 3), rnd.randint(2, 12)), glyph)
    d = ImageDraw.Draw(img)
    for _ in range(6):
        d.line([(rnd.randint(0, w), rnd.randint(0, h)), (rnd.randint(0, w), rnd.randint(0, h))], fill=(rnd.randint(90, 170),) * 3, width=2)
    for _ in range(260):
        d.point((rnd.randint(0, w - 1), rnd.randint(0, h - 1)), fill=(rnd.randint(60, 200),) * 3)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _digest(captcha_id: str, answer: str) -> str:
    return keys.mac("captcha", f"{captcha_id}:{answer.strip().upper()}")


def create(session) -> dict:
    session.execute(delete(Captcha).where(Captcha.expires_at < utcnow() - timedelta(hours=1)))   # opportunistic cleanup
    cid, text = new_id(), _random_text()
    session.add(Captcha(id=cid, answer_hash=_digest(cid, text), expires_at=utcnow() + timedelta(seconds=cfg.CAPTCHA_TTL_S)))
    session.flush()
    return {"captcha_id": cid, "image": "data:image/png;base64," + base64.b64encode(_render(text)).decode(), "expires_in": cfg.CAPTCHA_TTL_S}


def verify(session, captcha_id: str, answer: str) -> bool:
    """Consumes the CAPTCHA whether or not the answer is right, so each guess needs a fresh challenge."""
    row = session.execute(select(Captcha).where(Captcha.id == captcha_id)).scalar_one_or_none()
    if row is None:
        return False
    claimed = session.execute(update(Captcha).where(Captcha.id == captcha_id, Captcha.used_at.is_(None), Captcha.expires_at > utcnow())
                              .values(used_at=utcnow())).rowcount
    if claimed != 1:
        return False
    return hmac.compare_digest(row.answer_hash, _digest(captcha_id, answer or ""))
