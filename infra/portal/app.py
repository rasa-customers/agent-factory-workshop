"""The workshop portal: email in → capped LLM key, license link, and a local or cloud setup."""
from __future__ import annotations

import asyncio

import os
import re
import secrets
import shlex
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from infra.portal.db import Db

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
basic = HTTPBasic(auto_error=False)


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def setup_command(a: dict) -> str:
    repo = env("REPO_URL")
    folder = repo.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git") or "agent-factory-workshop"
    parts = ["./setup.sh", "--llm-key", a["llm_key"], "--base-url", env("PROXY_BASE_URL")]
    if a.get("license"):
        parts += ["--license", a["license"]]
    return f"git clone {repo} && cd {folder} && " + " ".join(shlex.quote(p) for p in parts)


def create_app(db: Db, minter: Any, pool: Any | None) -> FastAPI:
    app = FastAPI(title="Agent Factory Workshop")

    def current(request: Request) -> dict | None:
        return db.attendee_by_session(request.cookies.get("session"))

    def render(request: Request, name: str, **ctx: Any) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(request, name, {"env": env, **ctx})

    signup_lock = asyncio.Lock()

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request, code: str = ""):
        if current(request):
            return RedirectResponse("/me", status_code=303)
        return render(request, "index.html", error=None, code=code[:64], need_code=bool(env("EVENT_CODE")))

    @app.post("/signup")
    async def signup(request: Request, email: str = Form(...), code: str = Form("")):
        email = email.strip().lower()

        def refuse(msg: str, status: int) -> HTMLResponse:
            resp = render(request, "index.html", error=msg, code=code[:64], need_code=bool(env("EVENT_CODE")))
            resp.status_code = status
            return resp

        if not EMAIL.match(email):
            return refuse("That doesn't look like an email address.", 400)
        event_code = env("EVENT_CODE")
        if event_code and code.strip().lower() != event_code.strip().lower():
            return refuse("That event code isn't right — it's on the slide, or ask a Rasa person.", 403)
        async with signup_lock:  # look-up, mint and insert as one step: a double-click mints one key
            a = db.attendee(email)
            if a is None:
                if len(db.attendees()) >= int(env("SIGNUP_CAP") or 150):
                    return refuse("The workshop is full right now — ask a Rasa person to let you in.", 403)
                key = await minter.mint(email)
                token = secrets.token_urlsafe(24)
                db.add_attendee(email, key, token)
            else:
                token = a["session_token"]
        r = RedirectResponse("/me", status_code=303)
        r.set_cookie("session", token, max_age=60 * 60 * 24 * 7, httponly=True, samesite="lax")
        return r

    @app.get("/me", response_class=HTMLResponse)
    async def me(request: Request):
        a = current(request)
        if not a:
            return RedirectResponse("/", status_code=303)
        vm = db.vm(a["vm_id"])
        return render(request, "me.html", a=a, vm=vm, command=setup_command(a), cloud=pool is not None)

    @app.post("/license")
    async def license_(request: Request, license: str = Form(...)):
        a = current(request)
        if not a:
            return RedirectResponse("/", status_code=303)
        db.set_attendee(a["email"], license=license.strip())
        return RedirectResponse("/me", status_code=303)

    @app.post("/choose")
    async def choose(request: Request, choice: str = Form(...)):
        a = current(request)
        if not a:
            return RedirectResponse("/", status_code=303)
        if choice not in ("local", "cloud"):
            raise HTTPException(400, "choice must be local or cloud")
        db.set_attendee(a["email"], choice=choice)
        if choice == "cloud" and pool is not None:
            await pool.assign(a["email"])
        return RedirectResponse("/me", status_code=303)

    @app.get("/me/vm")
    async def me_vm(request: Request):
        a = current(request)
        if not a:
            raise HTTPException(401)
        if pool is None:
            return JSONResponse({"state": "unavailable"})
        return JSONResponse(await pool.status_for(a["email"]))

    @app.get("/internal/vm/{vm_id}/config")
    async def vm_config(vm_id: str, request: Request):
        vm = db.vm(vm_id)
        if not vm or not secrets.compare_digest(request.headers.get("x-config-secret", ""), vm["config_secret"] or ""):
            raise HTTPException(403)
        a = db.attendee(vm["attendee_email"]) if vm["attendee_email"] else None
        if not a:
            return {"assigned": False}
        cfg = {"OPENAI_API_KEY": a["llm_key"], "OPENAI_BASE_URL": env("PROXY_BASE_URL"),
               "PUBLIC_HOST": vm["hostname"]}
        if a.get("license"):
            cfg["RASA_LICENSE"] = a["license"]
        if env("STUDIO_KAFKA_URL"):
            cfg["STUDIO_KAFKA_URL"] = env("STUDIO_KAFKA_URL")
        return {"assigned": True, "password": vm["password"], "env": cfg}

    def admin_only(creds: HTTPBasicCredentials | None = Depends(basic)) -> None:
        pw = env("ADMIN_PASSWORD")
        if not creds or not pw or not secrets.compare_digest(creds.password, pw):
            raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})

    @app.get("/admin", response_class=HTMLResponse, dependencies=[Depends(admin_only)])
    async def admin(request: Request):
        people = db.attendees()
        for p in people:
            p["spend"] = await minter.spend(p["llm_key"])
        vms = db.vms()
        counts = {"total": len(people), "local": sum(p["choice"] == "local" for p in people),
                  "cloud": sum(p["choice"] == "cloud" for p in people),
                  "spend": round(sum(p["spend"] for p in people), 2),
                  "vm_states": {"launching": sum(v["state"] == "launching" and not v["attendee_email"] for v in vms),
                                "ready": sum(v["state"] == "ready" and not v["attendee_email"] for v in vms),
                                "assigned": sum(bool(v["attendee_email"]) and v["state"] != "terminated" for v in vms)}}
        return render(request, "admin.html", people=people, vms=vms, counts=counts)

    @app.post("/admin/scale", dependencies=[Depends(admin_only)])
    async def scale(n: int = Form(5)):
        if pool is None:
            raise HTTPException(400, "cloud machines are not enabled")
        await pool.scale(n)
        return RedirectResponse("/admin", status_code=303)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app
