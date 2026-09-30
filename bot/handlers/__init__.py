"""Handler routers, registered in dependency order."""

from __future__ import annotations

from aiogram import Dispatcher

from . import (
    admin,
    adminx,
    apps,
    build,
    extras,
    growth,
    panel,
    payment,
    pool,
    support,
    user,
    warp,
    webapp,
)


def register(dispatcher: Dispatcher) -> None:
    # ``payment`` goes first of all: it owns ``pay:`` and ``adm:pay`` callbacks,
    # the pre-checkout query and ``successful_payment``, and a payment update that
    # fell through to a broader router would be a payment nobody recorded.
    dispatcher.include_router(payment.router)
    # ``adminx`` and ``growth`` go next because they claim specific callbacks that
    # the older, broader routers would otherwise swallow: ``admin`` owns every
    # ``adm:`` callback and ``user`` owns the ``nav:`` ones.
    dispatcher.include_router(adminx.router)
    dispatcher.include_router(growth.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(build.router)
    dispatcher.include_router(panel.router)
    # Ahead of ``warp`` on purpose: the operator picker owns ``wg:net`` and has to
    # see it before the generic WARP router does.
    dispatcher.include_router(pool.router)
    dispatcher.include_router(warp.router)
    dispatcher.include_router(apps.router)
    dispatcher.include_router(support.router)
    dispatcher.include_router(webapp.router)
    dispatcher.include_router(extras.router)
    dispatcher.include_router(user.router)
