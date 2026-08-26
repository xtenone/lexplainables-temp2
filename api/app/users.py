"""Service-laag over de login-accounts in de database.

Verantwoordelijkheden:
  - Wachtwoord-hashing (bcrypt) + verificatie (constant-tijd via bcrypt zelf).
  - `verify_credentials`: **userid** + wachtwoord (+ optionele TOTP) → `User` of een reden-code,
    gebruikt door de auth-router waar de BFF (Auth.js) op inlogt. Inloggen gaat uitsluitend met de
    userid; `email` is een verplicht, uniek registratiegegeven (geen inlog-identiteit).
  - Eenmalige registratie: `needs_setup`/`bootstrap_admin` maken de allereerste beheerder zolang
    de tabel leeg is; daarna sluit die route.
  - Admin-CRUD voor gebruikersbeheer in /beheer, met de beleidsgaranties (laatste actieve
    beheerder mag niet verdwijnen).
  - Optionele 2FA (TOTP): koppelen (`begin_2fa`), bevestigen (`activate_2fa`) en losmaken
    (`disable_2fa`). Het secret staat versleuteld (Fernet, zie secrets_crypto).

Het wachtwoord-hash en het versleutelde TOTP-secret blijven binnen deze laag; de routers geven ze
nooit terug.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets

import bcrypt
import pyotp
from sqlalchemy import delete, func, insert, select, text, update

from . import db
from .secrets_crypto import crypto_beschikbaar, decrypt, decrypt_ttl, encrypt
from .user import ROLLEN, User, _utcnow

# TTL's voor de stateless auth-tokens (Fernet stempelt zelf de timestamp).
_LOGIN_TICKET_TTL_S = 5 * 60            # login-ticket: 5 min tussen wachtwoord- en 2FA-stap
_TRUSTED_DEVICE_TTL_S = 30 * 24 * 3600  # trusted device: 30 dagen 2FA overslaan

# Issuer-naam in de authenticator-app (bij het scannen van de QR zichtbaar als "Wetsanalyse").
_TOTP_ISSUER = "Wetsanalyse"

# Userid: 3–64 tekens, kleine letters/cijfers en . _ - (genormaliseerd lowercase).
_USERID_RE = re.compile(r"^[a-z0-9._-]{3,64}$")


class UserError(ValueError):
    """Ongeldige gebruiker-operatie (onbekend, dubbel, laatste beheerder, ongeldige rol, e.d.)."""


def _norm_userid(userid: str) -> str:
    return userid.strip().lower()


def _norm_email(email: str) -> str:
    return email.strip().lower()


def _row_to_user(row) -> User:
    m = dict(row)
    return User(
        userid=m["userid"],
        email=m["email"],
        password_hash=m["password_hash"],
        role=m["role"],
        totp_secret_enc=m["totp_secret_enc"],
        totp_enabled=m["totp_enabled"],
        active=m["active"],
        created=db.aware(m["created"]),
        updated=db.aware(m["updated"]),
    )


# --- wachtwoord-hashing --------------------------------------------------------

def hash_password(plain: str) -> str:
    # bcrypt kapt op 72 bytes; afdoende voor wachtwoorden. Hash bevat de salt.
    return bcrypt.hashpw(plain.encode("utf-8")[:72], bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("ascii"))
    except ValueError:
        return False


# Vaste dummy-hash om bij een onbekende/inactieve gebruiker toch de bcrypt-kost te betalen
# (constant-tijd responspad), zodat login-timing geen "bestaat + actief"-oracle wordt. Eén keer
# bij import berekend.
_DUMMY_HASH = hash_password("x")


def genereer_wachtwoord() -> str:
    """Tijdelijk wachtwoord bij aanmaken/resetten door een beheerder (eenmalig getoond)."""
    return secrets.token_urlsafe(12)


# --- lezen ---------------------------------------------------------------------

async def get_user(userid: str) -> User | None:
    async with db.get_engine().connect() as conn:
        row = (await conn.execute(
            select(db.users).where(db.users.c.userid == _norm_userid(userid))
        )).mappings().first()
    return _row_to_user(row) if row is not None else None


async def get_user_by_email(email: str) -> User | None:
    async with db.get_engine().connect() as conn:
        row = (await conn.execute(
            select(db.users).where(db.users.c.email == _norm_email(email))
        )).mappings().first()
    return _row_to_user(row) if row is not None else None


async def list_users() -> list[User]:
    async with db.get_engine().connect() as conn:
        rows = (await conn.execute(select(db.users).order_by(db.users.c.userid))).mappings().all()
    return [_row_to_user(r) for r in rows]


async def _count() -> int:
    async with db.get_engine().connect() as conn:
        return (await conn.execute(select(func.count()).select_from(db.users))).scalar() or 0


async def _aantal_actieve_beheerders() -> int:
    async with db.get_engine().connect() as conn:
        return (await conn.execute(
            select(func.count()).select_from(db.users).where(
                db.users.c.role == "beheerder", db.users.c.active.is_(True)
            )
        )).scalar() or 0


async def needs_setup() -> bool:
    """True zolang er nog geen enkel account is (de eenmalige-registratie-route is dan open)."""
    return await _count() == 0


# --- credential-verificatie ----------------------------------------------------

def _verify_totp(user: User, code: str) -> bool:
    if not user.totp_secret_enc:
        return False
    secret = decrypt(user.totp_secret_enc)
    # valid_window=1 vangt klok-drift van ±30s op.
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)


# --- stateless auth-tokens (login-ticket + trusted device) ---------------------
#
# Beide zijn Fernet-tokens (hergebruiken de LLM-master-key; 2FA vereist die toch al). Er is GEEN
# serverstate: het login-ticket draagt de al-geverifieerde userid naar het aparte 2FA-scherm zodat
# het wachtwoord daar niet nodig is; het trusted-device-token slaat de 2FA-prompt 30 dagen over en
# is gebonden aan sha256(password_hash + totp_secret_enc) — wijzigt het wachtwoord of gaat 2FA uit,
# dan verandert die binding en is het token vanzelf ongeldig (geen revocatielijst nodig).

def maak_login_ticket(userid: str) -> str | None:
    """Kortlevend bewijs 'wachtwoord geverifieerd voor userid X'. None als er geen master key is."""
    if not crypto_beschikbaar():
        return None
    return encrypt(json.dumps({"t": "ticket", "userid": userid}))


def lees_login_ticket(token: str | None) -> str | None:
    """Userid uit een geldig, niet-verlopen login-ticket; anders None."""
    if not token:
        return None
    plain = decrypt_ttl(token, _LOGIN_TICKET_TTL_S)
    if not plain:
        return None
    try:
        data = json.loads(plain)
    except ValueError:
        return None
    return data.get("userid") if data.get("t") == "ticket" else None


def _device_bind(user: User) -> str:
    """Bindwaarde die verandert bij wachtwoordwijziging of 2FA-uit → maakt een trusted-token dan
    automatisch ongeldig."""
    basis = f"{user.password_hash or ''}|{user.totp_secret_enc or ''}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def maak_trusted_device(user: User) -> str | None:
    """30-daags token dat op dit apparaat de 2FA-prompt overslaat. None zonder master key."""
    if not crypto_beschikbaar():
        return None
    return encrypt(json.dumps({"t": "trusted", "userid": user.userid, "bind": _device_bind(user)}))


async def valideer_trusted_device(token: str | None) -> str | None:
    """Userid als het trusted-device-token geldig, niet-verlopen en nog gebonden is (user actief,
    2FA aan, bind-match); anders None."""
    if not token:
        return None
    plain = decrypt_ttl(token, _TRUSTED_DEVICE_TTL_S)
    if not plain:
        return None
    try:
        data = json.loads(plain)
    except ValueError:
        return None
    if data.get("t") != "trusted" or not data.get("userid"):
        return None
    user = await get_user(data["userid"])
    if user is None or not user.active or not user.totp_enabled:
        return None
    if data.get("bind") != _device_bind(user):
        return None
    return user.userid


async def verify_credentials(
    userid: str, password: str, totp: str | None = None,
    *, ticket: str | None = None, trusted_token: str | None = None,
) -> tuple[User | None, str]:
    """Valideer inloggegevens (uitsluitend op userid). Geeft (user, "ok") of (None, reden).

    Reden-codes: "invalid" (onbekend/inactief/verkeerd wachtwoord — bewust niet onderscheiden om
    niets te lekken) en "totp_required" (wachtwoord klopt, maar 2FA staat aan en de code ontbreekt
    of is onjuist).

    Twee alternatieve bewijzen naast het wachtwoord:
    - `ticket`: een geldig login-ticket voor deze userid telt als wachtwoord-bewijs (voor het aparte
      2FA-scherm, dat het wachtwoord niet vasthoudt);
    - `trusted_token`: een geldig trusted-device-token slaat bij een 2FA-account de TOTP-stap over.
    """
    user = await get_user(userid)
    # Wachtwoord-bewijs via een geldig login-ticket voor DEZE userid, anders via het wachtwoord.
    ticket_ok = ticket is not None and lees_login_ticket(ticket) == userid
    if user is None or not user.active:
        if not ticket_ok:
            # Constant-tijd: betaal de bcrypt-kost ook bij een onbekende/inactieve user.
            verify_password(password, _DUMMY_HASH)
        return None, "invalid"
    if not ticket_ok and not verify_password(password, user.password_hash):
        return None, "invalid"
    if user.totp_enabled:
        if await valideer_trusted_device(trusted_token) == userid:
            return user, "ok"  # vertrouwd apparaat → 2FA overgeslagen
        if not totp or not _verify_totp(user, totp):
            return None, "totp_required"
    return user, "ok"


# --- validatie + insert --------------------------------------------------------

def _valideer_userid(userid: str) -> str:
    norm = _norm_userid(userid)
    if not _USERID_RE.match(norm):
        raise UserError("Ongeldige userid (3–64 tekens: kleine letters, cijfers, . _ -).")
    return norm


def _valideer_email(email: str) -> str:
    norm = _norm_email(email)
    if not norm or "@" not in norm:
        raise UserError("Ongeldig e-mailadres.")
    return norm


async def _insert_user(userid: str, email: str, password: str, *, role: str) -> User:
    if role not in ROLLEN:
        raise UserError(f"Onbekende rol: {role!r}")
    norm_id = _valideer_userid(userid)
    norm_email = _valideer_email(email)
    # Vooraf-checks op de twee unieke velden, voor duidelijke meldingen (de DB-constraints zijn de
    # uiteindelijke vangrail bij een race).
    if await get_user(norm_id) is not None:
        raise UserError(f"Userid bestaat al: {norm_id}")
    if await get_user_by_email(norm_email) is not None:
        raise UserError(f"E-mailadres bestaat al: {norm_email}")
    now = _utcnow()
    user = User(
        userid=norm_id, email=norm_email, password_hash=hash_password(password),
        role=role, created=now, updated=now,
    )
    try:
        async with db.get_engine().begin() as conn:
            await conn.execute(insert(db.users).values(
                userid=user.userid, email=user.email, password_hash=user.password_hash,
                role=user.role, totp_secret_enc=None, totp_enabled=False, active=True,
                created=now, updated=now,
            ))
    except Exception as e:  # IntegrityError op dubbele userid/email (race)
        raise UserError("Userid of e-mailadres bestaat al.") from e
    return user


# --- eenmalige registratie (bootstrap) -----------------------------------------

async def bootstrap_admin(userid: str, email: str, password: str) -> User:
    """Maak de allereerste beheerder — alleen zolang de tabel leeg is (anders UserError)."""
    if await _count() > 0:
        raise UserError("Er bestaat al een account; registratie is gesloten.")
    return await _insert_user(userid, email, password, role="beheerder")


# --- admin-CRUD ----------------------------------------------------------------

async def create_user(userid: str, email: str, role: str = "analist") -> tuple[User, str]:
    """Maak een account met een tijdelijk wachtwoord (eenmalig teruggegeven aan de beheerder)."""
    tijdelijk = genereer_wachtwoord()
    user = await _insert_user(userid, email, tijdelijk, role=role)
    return user, tijdelijk


async def _require_user(userid: str) -> User:
    user = await get_user(userid)
    if user is None:
        raise UserError(f"Onbekende gebruiker: {userid}")
    return user


async def set_role(userid: str, role: str) -> User:
    if role not in ROLLEN:
        raise UserError(f"Onbekende rol: {role!r}")
    user = await _require_user(userid)
    # Laatste actieve beheerder niet kunnen degraderen.
    if user.role == "beheerder" and role != "beheerder" and user.active:
        if await _aantal_actieve_beheerders() <= 1:
            raise UserError("Kan de laatste actieve beheerder niet degraderen.")
    await _update(user.userid, role=role)
    user.role = role
    return user


async def set_active(userid: str, active: bool) -> User:
    user = await _require_user(userid)
    if user.role == "beheerder" and user.active and not active:
        if await _aantal_actieve_beheerders() <= 1:
            raise UserError("Kan de laatste actieve beheerder niet deactiveren.")
    await _update(user.userid, active=active)
    user.active = active
    return user


async def patch_user(userid: str, *, role: str | None = None, active: bool | None = None) -> User:
    """Combineer een rol- en/of active-wijziging in ÉÉN transactie, met de 'laatste actieve
    beheerder'-invariant getoetst op de EIND-toestand. Zo kan een gelijktijdige rol+active-patch
    (of twee parallelle patches) de laatste beheerder niet via twee losse checks laten verdwijnen
    (TOCTOU). Op Postgres serialiseert een advisory xact-lock de check+write; op SQLite (tests) zijn
    writes al geserialiseerd."""
    if role is not None and role not in ROLLEN:
        raise UserError(f"Onbekende rol: {role!r}")
    user = await _require_user(userid)
    waarden: dict = {}
    if role is not None:
        waarden["role"] = role
    if active is not None:
        waarden["active"] = active
    if not waarden:
        return user
    nieuw_role = role if role is not None else user.role
    nieuw_active = active if active is not None else user.active
    was_actieve_beheerder = user.role == "beheerder" and user.active
    wordt_actieve_beheerder = nieuw_role == "beheerder" and nieuw_active
    waarden["updated"] = _utcnow()
    async with db.get_engine().begin() as conn:
        if was_actieve_beheerder and not wordt_actieve_beheerder:
            if db.get_engine().url.get_backend_name() == "postgresql":
                await conn.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": "actieve-beheerders"}
                )
            aantal = (await conn.execute(
                select(func.count()).select_from(db.users).where(
                    db.users.c.role == "beheerder", db.users.c.active.is_(True)
                )
            )).scalar() or 0
            if aantal <= 1:
                raise UserError("Kan de laatste actieve beheerder niet degraderen of deactiveren.")
        await conn.execute(update(db.users).where(db.users.c.userid == userid).values(**waarden))
    user.role, user.active = nieuw_role, nieuw_active
    return user


async def reset_password(userid: str) -> tuple[User, str]:
    """Zet een nieuw tijdelijk wachtwoord (eenmalig teruggegeven)."""
    user = await _require_user(userid)
    tijdelijk = genereer_wachtwoord()
    await _update(user.userid, password_hash=hash_password(tijdelijk))
    return user, tijdelijk


async def change_own_password(userid: str, current: str, nieuw: str) -> None:
    """Self-service wachtwoordwijziging: verifieer het huidige wachtwoord en zet een nieuw."""
    user = await _require_user(userid)
    if not user.active or not verify_password(current, user.password_hash):
        raise UserError("Huidig wachtwoord onjuist.")
    await _update(user.userid, password_hash=hash_password(nieuw))


async def delete_user(userid: str) -> None:
    user = await _require_user(userid)
    if user.role == "beheerder" and user.active and await _aantal_actieve_beheerders() <= 1:
        raise UserError("Kan de laatste actieve beheerder niet verwijderen.")
    async with db.get_engine().begin() as conn:
        await conn.execute(delete(db.users).where(db.users.c.userid == user.userid))


async def _update(userid: str, **waarden) -> None:
    waarden["updated"] = _utcnow()
    async with db.get_engine().begin() as conn:
        await conn.execute(update(db.users).where(db.users.c.userid == userid).values(**waarden))


# --- 2FA (TOTP) ----------------------------------------------------------------

async def begin_2fa(userid: str) -> str:
    """Genereer een (nog niet actief) TOTP-secret en geef de otpauth://-URI voor de QR-code.

    Het secret wordt versleuteld opgeslagen maar `totp_enabled` blijft False tot `activate_2fa`
    één geldige code bevestigt. Opnieuw aanroepen vervangt een nog niet bevestigd secret.
    """
    user = await _require_user(userid)
    secret = pyotp.random_base32()
    await _update(user.userid, totp_secret_enc=encrypt(secret), totp_enabled=False)
    # In de authenticator toont het account de userid; issuer = Wetsanalyse.
    return pyotp.TOTP(secret).provisioning_uri(name=user.userid, issuer_name=_TOTP_ISSUER)


async def activate_2fa(userid: str, code: str) -> None:
    user = await _require_user(userid)
    if not user.totp_secret_enc:
        raise UserError("Geen 2FA-aanmelding gestart; vraag eerst een nieuwe code aan.")
    if not _verify_totp(user, code):
        raise UserError("Onjuiste of verlopen code.")
    await _update(user.userid, totp_enabled=True)


async def disable_2fa(userid: str, code: str) -> None:
    user = await _require_user(userid)
    if not user.totp_enabled:
        raise UserError("2FA staat niet aan.")
    if not _verify_totp(user, code):
        raise UserError("Onjuiste of verlopen 2FA-code.")
    await _update(user.userid, totp_secret_enc=None, totp_enabled=False)
