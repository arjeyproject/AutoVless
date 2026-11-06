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
    proconsole,
    protocols,
    support,
    user,
    warp,
    webapp,
    wgpro,
)


def register(dispatcher: Dispatcher) -> None:
    # ``payment`` goes first of all: it owns ``pay:`` and ``adm:pay`` callbacks,
    # the pre-checkout query and ``successful_payment``, and a payment update that
    # fell through to a broader router would be a payment nobody recorded.
    dispatcher.include_router(payment.router)
    # ``adminx``, ``proconsole`` and ``growth`` go next because they claim specific
    # callbacks that the older, broader routers would otherwise swallow:
    # ``proconsole`` owns the whole ``adm:pro`` namespace, ``admin`` owns every
    # other ``adm:`` callback and ``user`` owns the ``nav:`` ones.
    dispatcher.include_router(adminx.router)
    dispatcher.include_router(proconsole.router)
    dispatcher.include_router(growth.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(build.router)
    dispatcher.include_router(panel.router)
    # ``protocols`` owns the ``proto:`` namespace (the selectable protocol menu,
    # per-protocol QR codes and the everything-at-once bundle). Its callbacks are
    # unique, so its place in the order only matters for the ``nav:protocols``
    # screen - registered early so no broader router can swallow it.
    dispatcher.include_router(protocols.router)
    # ``wgpro`` and ``pool`` sit ahead of ``warp`` on purpose: the 3.0 layer owns
    # ``wg:set``, ``wg:backup``, ``wg:restore`` and ``wg:bench``, and the operator
    # picker owns ``wg:net`` - both have to be seen before the generic WARP router.
    dispatcher.include_router(wgpro.router)
    dispatcher.include_router(pool.router)
    dispatcher.include_router(warp.router)
    dispatcher.include_router(apps.router)
    dispatcher.include_router(support.router)
    dispatcher.include_router(webapp.router)
    dispatcher.include_router(extras.router)
    dispatcher.include_router(user.router)
