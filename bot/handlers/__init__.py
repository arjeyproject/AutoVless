"""Handler routers, registered in dependency order."""

from __future__ import annotations

from aiogram import Dispatcher

from . import admin, apps, build, extras, panel, support, user, warp, webapp


def register(dispatcher: Dispatcher) -> None:
    dispatcher.include_router(admin.router)
    dispatcher.include_router(build.router)
    dispatcher.include_router(panel.router)
    dispatcher.include_router(warp.router)
    dispatcher.include_router(apps.router)
    dispatcher.include_router(support.router)
    dispatcher.include_router(webapp.router)
    dispatcher.include_router(extras.router)
    dispatcher.include_router(user.router)
