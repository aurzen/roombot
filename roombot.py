from __future__ import annotations

import asyncio

import TOKENS
import aurcore
import aurflux
from roomhandler import RoomHandler
import typing as ty
from loguru import logger
from discord import Intents
if ty.TYPE_CHECKING:
   from aurflux.command import *


class Roombot:
   def __init__(self):
      self.event_router = aurcore.event.EventRouterHost(name=self.__class__.__name__)
      self.flux = aurflux.FluxClient(self.__class__.__name__, admin_id=TOKENS.ADMIN_ID, parent_router=self.event_router, intents=Intents().all())

      @self.flux.router.listen_for(":ready")
      def rdy(event: aurflux.FluxEvent):
         asyncio.get_running_loop().create_task(self.clock())

   async def startup(self, token: str):
      logger.info(self.event_router)
      logger.info("a\nb")
      await self.flux.start(token)

   async def shutdown(self):
      await self.flux.logout()

   async def clock(self):
      print("Clock started")
      await self.event_router.submit(aurflux.FluxEvent(self.flux, "roomhandler:tock"))
      await asyncio.sleep(60 * 60 * 2)


roombot = Roombot()
roombot.flux.register_cog(RoomHandler)
logger.info(roombot.event_router)

aurcore.aiorun(roombot.startup(token=TOKENS.ROOMBOT), roombot.shutdown())
