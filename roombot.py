from __future__ import annotations

import asyncio

import TOKENS
import aurcore
import aurflux
from aurflux.argh import *
from roomhandler import RoomHandler

if ty.TYPE_CHECKING:
    from aurflux.command import *


class Roombot:
    def __init__(self):
        self.event_router = aurcore.event.EventRouter(name=self.__class__.__name__)
        self.flux = aurflux.Aurflux(self.__class__.__name__, admin_id=TOKENS.ADMIN_ID, parent_router=self.event_router)

        @self.flux.router.endpoint(":ready")
        def rdy(event: aurcore.event.Event):
            asyncio.get_running_loop().create_task(self.clock())

    async def startup(self, token: str):
        await self.flux.start(token)

    async def shutdown(self):
        await self.flux.logout()

    async def clock(self):
        await self.event_router.submit(aurcore.Event(":tock"))
        await asyncio.sleep(60 * 60 * 2)


roombot = Roombot()
roombot.flux.register_cog(RoomHandler)

aurcore.aiorun(roombot.startup(token=TOKENS.ROOMBOT), roombot.shutdown())
