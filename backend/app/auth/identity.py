"""Email and name validation. A syntactically valid address is NOT trusted: ownership is proven by the emailed code."""
import re
import unicodedata

from email_validator import EmailNotValidError, validate_email

from app.core import config as cfg

DISPOSABLE = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org", "sharklasers.com", "grr.la", "10minutemail.com",
    "10minutemail.net", "tempmail.com", "temp-mail.org", "temp-mail.io", "tempmail.net", "tempmailo.com", "throwawaymail.com",
    "yopmail.com", "yopmail.net", "yopmail.fr", "trashmail.com", "trashmail.net", "getnada.com", "nada.email", "maildrop.cc",
    "dispostable.com", "fakeinbox.com", "mailnesia.com", "mintemail.com", "mytemp.email", "mohmal.com", "emailondeck.com",
    "burnermail.io", "spamgourmet.com", "mailcatch.com", "moakt.com", "tmail.ws", "tmpmail.org", "tmpmail.net", "dropmail.me",
    "harakirimail.com", "mail.tm", "inboxkitten.com", "spambox.us", "33mail.com", "anonaddy.me", "guerrillamailblock.com",
    "minuteinbox.com", "luxusmail.org", "discard.email", "discardmail.com", "crazymailing.com", "fakemailgenerator.com",
}


class InvalidIdentity(ValueError):
    pass


def normalize_email(raw: str) -> str:
    """Validate and canonicalise an email. Raises InvalidIdentity with a user-safe message."""
    if not isinstance(raw, str) or len(raw) > 254:
        raise InvalidIdentity("Enter a valid email address")
    raw = unicodedata.normalize("NFKC", raw).strip()
    if any(ord(c) < 32 or c in "\r\n\t<>\"'`\\,;()[]{}" for c in raw):       # header-injection / markup / template characters
        raise InvalidIdentity("Enter a valid email address")
    try:
        info = validate_email(raw, check_deliverability=cfg.AUTH_CHECK_MX)   # syntax + (in production) the domain can receive mail
    except EmailNotValidError:
        raise InvalidIdentity("Enter a valid email address that can receive mail")
    email = info.normalized.lower()
    domain = email.rsplit("@", 1)[1]
    if any(domain == d or domain.endswith("." + d) for d in DISPOSABLE):
        raise InvalidIdentity("Disposable email addresses are not allowed")
    if cfg.ALLOWED_EMAIL_DOMAINS and domain not in cfg.ALLOWED_EMAIL_DOMAINS:
        raise InvalidIdentity("Sign-up is restricted to approved email domains")
    return email


def _is_letter(c: str) -> bool:
    return unicodedata.category(c).startswith("L")


def _is_name_char(c: str) -> bool:
    """Letters (L*) and combining marks (M*) in any script. Marks matter: Hindi/Telugu/Tamil vowel signs and viramas are
    category M, so `str.isalpha()` would wrongly reject real names like 'अनिल' or 'అనిల్'."""
    return unicodedata.category(c)[0] in "LM" or c in " .'-"


def validate_full_name(raw: str) -> str:
    """Letters and marks (any script), spaces, dots, apostrophes and hyphens only: no markup, quotes or control characters."""
    name = " ".join(unicodedata.normalize("NFKC", raw).split())
    ok = 2 <= len(name) <= 80 and all(_is_name_char(c) for c in name) and any(_is_letter(c) for c in name)
    ok = ok and _is_letter(name[0]) and (name[-1] not in " '-") and not re.search(r"[.'-]{2,}", name)   # O'Brien, Mary-Jane, J. R. Tolkien: yes; "--", "'-", "..": no
    if not ok:
        raise InvalidIdentity("Name must be 2-80 characters: letters, spaces, dots, apostrophes and hyphens only")
    return name
