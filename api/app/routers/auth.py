"""Auth-resource (gemount onder /v1/auth) — login-verificatie, eenmalige registratie en 2FA.

De **enige client is de frontend-BFF**: deze endpoints zitten achter de bestaande client-bearer
(`require_client`). De BFF (Auth.js) verifieert hier inloggegevens en zet voor de self-service
2FA-/account-endpoints een **vertrouwde `X-User-Id`-header** uit de ingelogde sessie — die identiteit
komt dus nooit uit browser-input. Inloggen gaat uitsluitend met de **userid**; `email` is een
verplicht, uniek registratiegegeven. De API blijft de identiteitsbron; de BFF houdt alleen de sessie.

GET  /v1/auth/setup-status        — is er nog geen account? (dan staat de registratie open)
POST /v1/auth/setup               — maak de allereerste beheerder (alleen bij lege tabel → anders 409)
POST /v1/auth/verify              — valideer userid + wachtwoord (+ optionele TOTP)
GET  /v1/auth/me                  — eigen account (rol + of 2FA aanstaat) — X-User-Id
POST /v1/auth/change-password     — eigen wachtwoord wijzigen (huidig → nieuw) — X-User-Id
POST /v1/auth/2fa/begin           — start 2FA-koppeling, geeft de otpauth-URI — X-User-Id
POST /v1/auth/2fa/activate        — bevestig 2FA met één geldige code — X-User-Id
POST /v1/auth/2fa/disable         — schakel 2FA uit — X-User-Id
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from .. import ratelimit, users
from ..auth import require_client
from ..secrets_crypto import SecretsCryptoError, crypto_beschikbaar

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(require_client)])


# --- modellen ------------------------------------------------------------------

class SetupStatus(BaseModel):
    needs_setup: bool


class SetupIn(BaseModel):
    userid: str = Field(max_length=64)
    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=512)


class VerifyIn(BaseModel):
    userid: str = Field(max_length=64)
    # Wachtwoord is optioneel: het 2FA-scherm bewijst de identiteit via `ticket` i.p.v. het wachtwoord.
    password: str = Field(default="", max_length=512)
    totp: str | None = Field(default=None, max_length=16)
    # Login-ticket (wachtwoord-bewijs voor de 2FA-stap) en trusted-device-token (2FA overslaan);
    # beide server→server via httpOnly cookies, nooit direct uit browser-input. Ruime cap: Fernet-tokens.
    ticket: str | None = Field(default=None, max_length=1024)
    trusted_token: str | None = Field(default=None, max_length=1024)
    # Vraagt (bij een geslaagde 2FA) om een trusted-device-token voor "30 dagen onthouden".
    remember: bool = False


class VerifyResult(BaseModel):
    """Intern contract voor de BFF (Auth.js). 200 met `ok=false` i.p.v. 401 zodat de
    authorize()-flow zonder exception-afhandeling de reden kan lezen. `ticket`/`trusted_token`
    gaan server→server naar de BFF, die ze als httpOnly cookies zet (nooit naar de browser-JS)."""
    ok: bool
    code: str = ""  # "" | "invalid" | "totp_required"
    userid: str = ""
    email: str = ""
    role: str = ""
    ticket: str | None = None          # bij totp_required: bewijs voor het aparte 2FA-scherm
    trusted_token: str | None = None   # bij ok + remember: 30-daags "dit apparaat onthouden"-token


class MeOut(BaseModel):
    userid: str
    email: str
    role: str
    totp_enabled: bool


class TotpBeginOut(BaseModel):
    otpauth_uri: str


class TotpActivateIn(BaseModel):
    totp: str = Field(max_length=16)


class TotpDisableIn(BaseModel):
    totp: str = Field(max_length=16)


class PasswordChangeIn(BaseModel):
    current: str = Field(max_length=512)
    new: str = Field(min_length=8, max_length=512)


# --- helpers -------------------------------------------------------------------

async def huidige_userid(x_user_id: str | None = Header(default=None)) -> str:
    """De ingelogde gebruiker, door de BFF uit de sessie in `X-User-Id` gezet."""
    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geen gebruikerscontext.")
    return x_user_id


# --- registratie + login -------------------------------------------------------

@router.get("/setup-status", response_model=SetupStatus)
async def setup_status():
    return SetupStatus(needs_setup=await users.needs_setup())


@router.post("/setup", response_model=MeOut, status_code=status.HTTP_201_CREATED)
async def setup(body: SetupIn):
    try:
        user = await users.bootstrap_admin(body.userid, body.email, body.password)
    except users.UserError as e:
        # Tabel niet meer leeg, of ongeldige invoer → registratie gesloten/ongeldig.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return MeOut(userid=user.userid, email=user.email, role=user.role, totp_enabled=user.totp_enabled)


@router.post("/verify", response_model=VerifyResult)
async def verify(body: VerifyIn):
    if not ratelimit.login_allowed(body.userid):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Te veel inlogpogingen; probeer later opnieuw.",
        )
    try:
        user, code = await users.verify_credentials(
            body.userid, body.password, body.totp,
            ticket=body.ticket, trusted_token=body.trusted_token,
        )
    except SecretsCryptoError:
        # 2FA staat aan maar het secret kan niet ontsleuteld worden (master key weg/geroteerd).
        return VerifyResult(ok=False, code="invalid")
    if user is None:
        # Wachtwoord klopte maar 2FA is nog nodig → geef een login-ticket mee zodat het aparte
        # 2FA-scherm de identiteit heeft zonder het wachtwoord opnieuw te hoeven vasthouden.
        ticket = users.maak_login_ticket(body.userid) if code == "totp_required" else None
        return VerifyResult(ok=False, code=code, ticket=ticket)
    # Bij een geslaagde 2FA-login met "onthouden" aangevinkt: een 30-daags trusted-device-token.
    trusted = (
        users.maak_trusted_device(user)
        if body.remember and user.totp_enabled
        else None
    )
    return VerifyResult(
        ok=True, code="ok", userid=user.userid, email=user.email, role=user.role,
        trusted_token=trusted,
    )


# --- self-service account + 2FA ------------------------------------------------

@router.get("/me", response_model=MeOut)
async def me(userid: str = Depends(huidige_userid)):
    user = await users.get_user(userid)
    if user is None or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account niet (meer) actief.")
    return MeOut(userid=user.userid, email=user.email, role=user.role, totp_enabled=user.totp_enabled)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: PasswordChangeIn, userid: str = Depends(huidige_userid)):
    try:
        await users.change_own_password(userid, body.current, body.new)
    except users.UserError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/2fa/begin", response_model=TotpBeginOut)
async def tfa_begin(userid: str = Depends(huidige_userid)):
    if not crypto_beschikbaar():
        raise HTTPException(
            status_code=400,
            detail="Geen LLM_CONFIG_SECRET geconfigureerd; 2FA-secret kan niet versleuteld worden opgeslagen.",
        )
    try:
        uri = await users.begin_2fa(userid)
    except users.UserError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return TotpBeginOut(otpauth_uri=uri)


@router.post("/2fa/activate", status_code=status.HTTP_204_NO_CONTENT)
async def tfa_activate(body: TotpActivateIn, userid: str = Depends(huidige_userid)):
    try:
        await users.activate_2fa(userid, body.totp)
    except users.UserError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def tfa_disable(body: TotpDisableIn, userid: str = Depends(huidige_userid)):
    try:
        await users.disable_2fa(userid, body.totp)
    except users.UserError as e:
        raise HTTPException(status_code=400, detail=str(e))
