from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def detect_lang(request: Request, lang_param: str | None) -> str:
    if lang_param in ("en", "ja"):
        return lang_param
    accept = request.headers.get("accept-language", "")
    if "ja" in accept.lower():
        return "ja"
    return "en"


@router.get("/", response_class=HTMLResponse)
async def landing(
    request: Request,
    lang: str | None = Query(default=None),
):
    resolved_lang = detect_lang(request, lang)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    base_url = f"{scheme}://{request.url.hostname}"
    if request.url.port and request.url.port not in (80, 443):
        base_url += f":{request.url.port}"
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={"lang": resolved_lang, "base_url": base_url},
    )
