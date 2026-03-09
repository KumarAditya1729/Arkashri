from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth

from arkashri.config import get_settings

router = APIRouter()
oauth = OAuth()

# We will initialize the oauth provider dynamically within the route to have access to settings
# or we can do it lazily.
_oauth_initialized = False

def init_oauth():
    global _oauth_initialized
    if _oauth_initialized:
        return
    settings = get_settings()
    if settings.oauth_client_id and settings.oauth_server_metadata_url:
        oauth.register(
            name='enterprise_oidc',
            client_id=settings.oauth_client_id,
            client_secret=settings.oauth_client_secret,
            server_metadata_url=settings.oauth_server_metadata_url,
            client_kwargs={
                'scope': 'openid email profile'
            }
        )
        _oauth_initialized = True

@router.get("/login")
async def login(request: Request, redirect_uri: str | None = None):
    init_oauth()
    settings = get_settings()
    if not settings.oauth_client_id:
        raise HTTPException(status_code=501, detail="OAuth is not configured on this server.")
    
    # Normally redirect_uri comes from request.url_for('auth_callback')
    # but we'll use a hardcoded or provided one for flexibility
    if not redirect_uri:
        host = request.headers.get("host", "localhost:8000")
        redirect_uri = f"{request.url.scheme}://{host}/api/v1/auth/callback"
        
    return await oauth.enterprise_oidc.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def auth_callback(request: Request):
    init_oauth()
    try:
        token = await oauth.enterprise_oidc.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")
    
    user = token.get('userinfo')
    if user:
        request.session['user'] = dict(user)
        
        # Log the login
        from arkashri.db import AsyncSessionLocal
        from arkashri.services.audit_log import log_system_event
        async with AsyncSessionLocal() as db:
            await log_system_event(
                db,
                tenant_id="OIDC_PROVIDER", # Or actual tenant if mapping exists
                user_email=user.get("email"),
                action="USER_SESSION_STARTED",
                resource_type="USER",
                request=request
            )
            
    # Redirect to frontend
    return RedirectResponse(url="/")


@router.get("/logout")
async def logout(request: Request):
    user = request.session.get('user')
    if user:
        # Log the logout
        from arkashri.db import AsyncSessionLocal
        from arkashri.services.audit_log import log_system_event
        async with AsyncSessionLocal() as db:
            await log_system_event(
                db,
                tenant_id="OIDC_PROVIDER",
                user_email=user.get("email"),
                action="USER_SESSION_ENDED",
                resource_type="USER",
                request=request
            )
    request.session.pop('user', None)
    return RedirectResponse(url="/")


@router.get("/me")
async def get_current_user(request: Request):
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
