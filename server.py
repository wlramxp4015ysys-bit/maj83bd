"""
Async REST API Backend for A2 TV App.
Powered by aiohttp.web with CORS support and JSON endpoints.
"""

import json
from aiohttp import web
from config import API_HOST, API_PORT, APP_PACKAGE, CURRENT_APP_VERSION_CODE
from database import db

# CORS Middleware to allow requests from Android WebView
@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        response = web.Response(status=200)
    else:
        try:
            response = await handler(request)
        except web.HTTPException as ex:
            response = ex
        except Exception as e:
            response = web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, X-Admin-Key"
    return response

DEFAULT_MAINTENANCE_MSG = "التطبيق تحت الصيانة حالياً، نعمل على تحسين تجربتك. يرجى المحاولة لاحقاً"

PROTECTED_ENDPOINTS = {
    "/api/channels",
    "/api/categories",
    "/api/channel-apis"
}

@web.middleware
async def maintenance_middleware(request, handler):
    path = request.path.rstrip("/")
    if path in PROTECTED_ENDPOINTS:
        m = db.get_maintenance()
        if m.get("enabled", False):
            # Check for admin authentication bypass
            auth = request.headers.get("Authorization", "")
            admin_key = request.headers.get("X-Admin-Key", "")
            query_token = request.query.get("token", "")
            from config import SECRET_KEY
            is_admin = (auth and (SECRET_KEY in auth)) or (admin_key == SECRET_KEY) or (query_token == SECRET_KEY)
            if not is_admin:
                msg = m.get("message") or DEFAULT_MAINTENANCE_MSG
                return json_ar({
                    "status": "maintenance",
                    "maintenance": True,
                    "message": msg,
                    "updated_at": m.get("updated_at", "")
                }, status=503)

    return await handler(request)

def json_ar(data, status=200):
    return web.json_response(data, status=status, dumps=lambda obj: json.dumps(obj, ensure_ascii=False))

# Routes Handlers
async def handle_root(request):
    return json_ar({
        "status": "online",
        "service": "A2 TV Backend API & Telegram Bot",
        "version": "2.0.0",
        "package": APP_PACKAGE,
        "endpoints": {
            "app_config": "/api/app-config",
            "channels": "/api/channels",
            "categories": "/api/categories",
            "maintenance": "/api/maintenance",
            "update": "/api/update",
            "channel_apis": "/api/channel-apis"
        }
    })

async def handle_app_config(request):
    """Returns combined app configuration (maintenance, update, and channels overview)."""
    maintenance = db.get_maintenance()
    update_info = db.get_app_update()
    channels = db.get_channels()
    categories = db.get_categories()
    latest_notif = sanitize_notif(db.get_latest_notification())
    sound_info = db.get_notification_sound()
    apis = db.get_channel_apis()

    return json_ar({
        "status": "success",
        "package": APP_PACKAGE,
        "maintenance": maintenance,
        "update": update_info,
        "notification": latest_notif,
        "notification_sound": sanitize_url(sound_info.get("url", "")),
        "notification_sound_name": sound_info.get("name", "افتراضي"),
        "counts": {
            "channels": len(channels),
            "categories": len(categories),
            "apis": len(apis)
        }
    })

from config import API_HOST, API_PORT, APP_PACKAGE, CURRENT_APP_VERSION_CODE, PUBLIC_URL
import os

def sanitize_url(u):
    if not u or not isinstance(u, str):
        return u
    u = u.strip()
    if u.startswith("http://0.0.0.0:8080") or u.startswith("http://127.0.0.1:8080"):
        part = u.split(":8080", 1)[1]
        return f"{PUBLIC_URL}{part}"
    if u.startswith("/static/") or u.startswith("/uploads/"):
        return f"{PUBLIC_URL}{u}"
    return u

def sanitize_notif(n):
    if not n or not isinstance(n, dict):
        return n
    res = dict(n)
    if "image" in res:
        res["image"] = sanitize_url(res["image"])
    if "sound" in res:
        res["sound"] = sanitize_url(res["sound"])
    return res

async def handle_categories(request):
    """Returns channel categories, optionally filtered by api_id."""
    api_id = request.query.get("api_id", None)
    include_hidden = request.query.get("include_hidden", "false").lower() in ("true", "1")
    categories = db.get_categories(api_id)
    if not include_hidden:
        categories = [c for c in categories if not c.get("hidden", False)]
    
    # Sanitize category image URLs
    for c in categories:
        if c.get("image"):
            c["image"] = sanitize_url(c["image"])

    return json_ar({
        "status": "success",
        "count": len(categories),
        "filter_api": api_id or "all",
        "categories": categories
    })

async def handle_channels(request):
    """Returns all channels or filtered by category, api_id, or search query."""
    category = request.query.get("category", None)
    api_id = request.query.get("api_id", None)
    search_q = request.query.get("q", request.query.get("search", None))
    include_disabled = request.query.get("include_disabled", "false").lower() in ("true", "1")

    if search_q:
        channels = db.search_channels(search_q, category)
    else:
        channels = db.get_channels(category)

    if not include_disabled:
        channels = [c for c in channels if not c.get("disabled", False)]

    if api_id and api_id != "all":
        channels = [c for c in channels if c.get("api_id") == api_id]

    # Sanitize channel logos
    for ch in channels:
        if ch.get("logo"):
            ch["logo"] = sanitize_url(ch["logo"])

    return json_ar({
        "status": "success",
        "filter": category or "all",
        "filter_api": api_id or "all",
        "search": search_q or "",
        "count": len(channels),
        "channels": channels
    })

async def handle_export_m3u(request):
    """Exports all active channels in standard IPTV M3U format."""
    category = request.query.get("category", None)
    m3u_text = db.export_channels_m3u(category)
    return web.Response(
        text=m3u_text,
        content_type="audio/x-mpegurl",
        headers={
            "Content-Disposition": 'attachment; filename="a2tv_playlist.m3u"',
            "Access-Control-Allow-Origin": "*"
        }
    )

async def handle_stats(request):
    """Returns comprehensive channel and category statistics."""
    stats = db.get_channel_stats()
    return json_ar({
        "status": "success",
        "stats": stats
    })

async def handle_maintenance(request):
    """Returns maintenance status."""
    maintenance = db.get_maintenance()
    return json_ar({
        "status": "success",
        "maintenance": maintenance
    })

async def handle_update(request):
    """Checks if there is a new update available for the app."""
    update_info = db.get_app_update()
    try:
        current_v = int(request.query.get("current_version", CURRENT_APP_VERSION_CODE))
    except (ValueError, TypeError):
        current_v = CURRENT_APP_VERSION_CODE

    has_update = update_info.get("enabled", False) and (update_info.get("version_code", 0) > current_v)

    return json_ar({
        "status": "success",
        "current_version": current_v,
        "has_update": has_update,
        "update": update_info
    })

async def handle_channel_apis(request):
    """Returns list of active channel APIs."""
    apis = db.get_channel_apis()
    return json_ar({
        "status": "success",
        "count": len(apis),
        "apis": apis
    })

async def handle_notifications(request):
    """Returns latest push notifications."""
    limit = int(request.query.get("limit", 10))
    notifs = [sanitize_notif(n) for n in db.get_notifications(limit=limit)]
    latest = sanitize_notif(db.get_latest_notification())
    sound_info = db.get_notification_sound()
    return json_ar({
        "status": "success",
        "count": len(notifs),
        "latest": latest,
        "notification_sound": sanitize_url(sound_info.get("url", "")),
        "notifications": notifs
    })

async def handle_fcm_register(request):
    """Registers or updates a client FCM device token."""
    try:
        data = await request.json()
        token = data.get("token", "").strip()
        device_id = data.get("device_id", "").strip()
        model = data.get("model", "").strip()
        version = data.get("version", "").strip()
        platform = data.get("platform", "android").strip()
        if not token:
            return json_ar({"status": "error", "message": "token is required"}, status=400)
        ok, res = db.register_device_token(token, device_id=device_id, model=model, app_version=version, platform=platform)
        return json_ar({"status": "success", "device": res})
    except Exception as e:
        return json_ar({"status": "error", "message": str(e)}, status=500)

async def handle_fcm_unregister(request):
    """Unregisters a client FCM device token."""
    try:
        data = await request.json()
        token = data.get("token", "").strip()
        if not token:
            return json_ar({"status": "error", "message": "token is required"}, status=400)
        ok = db.unregister_device_token(token)
        return json_ar({"status": "success", "unregistered": ok})
    except Exception as e:
        return json_ar({"status": "error", "message": str(e)}, status=500)

async def handle_fcm_stats(request):
    """Returns FCM device registration statistics."""
    from fcm_sender import is_firebase_configured
    tokens = db.get_all_fcm_tokens()
    return json_ar({
        "status": "success",
        "registered_devices": len(tokens),
        "firebase_configured": is_firebase_configured()
    })

def make_app():
    app = web.Application(middlewares=[cors_middleware, maintenance_middleware])
    app.router.add_get("/", handle_root)
    app.router.add_get("/api/app-config", handle_app_config)
    app.router.add_get("/api/app-config/", handle_app_config)
    app.router.add_get("/api/config", handle_app_config)
    app.router.add_get("/api/config/", handle_app_config)
    
    app.router.add_get("/api/categories", handle_categories)
    app.router.add_get("/api/categories/", handle_categories)
    
    app.router.add_get("/api/channels", handle_channels)
    app.router.add_get("/api/channels/", handle_channels)

    app.router.add_get("/api/export/m3u", handle_export_m3u)
    app.router.add_get("/api/export/m3u/", handle_export_m3u)

    app.router.add_get("/api/stats", handle_stats)
    app.router.add_get("/api/stats/", handle_stats)
    
    app.router.add_get("/api/maintenance", handle_maintenance)
    app.router.add_get("/api/maintenance/", handle_maintenance)
    
    app.router.add_get("/api/update", handle_update)
    app.router.add_get("/api/update/", handle_update)
    
    app.router.add_get("/api/channel-apis", handle_channel_apis)
    app.router.add_get("/api/channel-apis/", handle_channel_apis)

    app.router.add_get("/api/notifications", handle_notifications)
    app.router.add_get("/api/notifications/", handle_notifications)

    app.router.add_post("/api/fcm/register", handle_fcm_register)
    app.router.add_post("/api/fcm/register/", handle_fcm_register)
    app.router.add_post("/api/fcm/unregister", handle_fcm_unregister)
    app.router.add_post("/api/fcm/unregister/", handle_fcm_unregister)
    app.router.add_get("/api/fcm/stats", handle_fcm_stats)
    app.router.add_get("/api/fcm/stats/", handle_fcm_stats)

    uploads_dir = os.path.join(os.path.dirname(__file__), "data", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    app.router.add_static("/static/uploads/", path=uploads_dir, show_index=False)
    app.router.add_static("/uploads/", path=uploads_dir, show_index=False)

    updates_dir = os.path.join(os.path.dirname(__file__), "data", "updates")
    os.makedirs(updates_dir, exist_ok=True)
    app.router.add_static("/static/", path=updates_dir, show_index=False)

    return app

def run_server(host=API_HOST, port=API_PORT, handle_signals=False):
    app = make_app()
    web.run_app(app, host=host, port=port, handle_signals=handle_signals, print=print)

if __name__ == "__main__":
    run_server(handle_signals=True)
