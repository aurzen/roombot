from __future__ import annotations

import argparse
import asyncio
import base64
import re
import typing as ty
from datetime import datetime, timedelta

import aurflux
import aurflux.auth
import aurflux.command
import discord
from aurflux.command import Response
from loguru import logger

logger.add("stdout", backtrace=True, diagnose=True)


def MemberIDType(arg: str) -> int:
   match = re.search(r"<@?!?(\d*)>", arg)
   if not match:
      raise argparse.ArgumentError
   return int(match.group(1))


# noinspection PyPep8Naming
class CHANNEL_PERMS:
   BOT = discord.PermissionOverwrite(
      read_messages=True,
      send_messages=True,
      # add_reactions=True,
      # manage_channels=True,
      # manage_permissions=True
   )
   USER = discord.PermissionOverwrite(
      read_messages=True,
      send_messages=True)
   FORBIDDEN = discord.PermissionOverwrite(
      read_messages=False,
      send_messages=False)


def get_moderator_roles(guild: discord.Guild) -> ty.List[discord.Role]:
   return [role for role in guild.roles if role.permissions.ban_members]


def get_moderator_overwrite(guild: discord.Guild) -> ty.Dict[discord.Role, discord.PermissionOverwrite]:
   return {
      guild.get_role(426487509183234060): CHANNEL_PERMS.USER,
      guild.get_role(426487602691047460): CHANNEL_PERMS.USER
   }


def str_2_base64(s: str):
   return base64.urlsafe_b64encode(s.encode("ascii")).decode("ascii")


def base64_2_str(s: str):
   return base64.urlsafe_b64decode(s.encode("ascii")).decode("ascii")


def overwrites_base(guild: discord.Guild):
   return {
      # guild.default_role: CHANNEL_PERMS.FORBIDDEN,
      guild.me          : CHANNEL_PERMS.BOT
   }


async def lock_room(channel: discord.TextChannel, allow_moderators=False):
   overwrites_dict = overwrites_base(channel.guild)

   overwrites_dict = {**{target: None for target in channel.members}, **overwrites_dict}

   if allow_moderators:
      overwrites_dict.update(**get_moderator_overwrite(channel.guild))

   await asyncio.gather(*[
      channel.set_permissions(target, overwrite=overwrite)
      for target, overwrite in overwrites_dict.items()
   ])


class RoomHandler(aurflux.cog.FluxCog):
   last_seen_cache: ty.Dict[discord.TextChannel, discord.Message] = {}

   def load(self):
      @self._commandeer(name="chat", default_auths=[aurflux.auth.Record.allow_all()])
      async def _(ctx: aurflux.ty.GuildCommandCtx, targets_raw):
         """
         chat *<member>
         ==
         Creates a chat room with each member in `*<member>`
         ==
         *<member> : The members to create a room with
         ==
         :param ctx:
         :param targets_raw:
         :return:
         """
         member_ids = aurflux.utils.find_mentions(targets_raw)
         logger.error(member_ids)
         logger.error(ctx.msg_ctx.author.id)
         members = [await ctx.flux.get_member_s(ctx.msg_ctx.guild, member_id) for member_id in (set(member_ids) | {ctx.msg_ctx.author.id})]
         logger.error(members)
         if len(members) < 2:
            return aurflux.command.Response(f"Please create a room with at least 2 people!", status="error")

         overwrites_dict = {**overwrites_base(ctx.msg_ctx.guild), **{target: CHANNEL_PERMS.USER for target in members}}
         print(overwrites_dict)
         text_channel = await ctx.msg_ctx.guild.create_text_channel(
            name="-".join([member.name for member in members]),
            category=None,  # todo: add category?
            # overwrites=overwrites_dict
         )
         for k,v in overwrites_dict.items():
           logger.info(k)
           logger.info(v)
           await text_channel.set_permissions(k, overwrite=v)

         await text_channel.set_permissions(ctx.msg_ctx.guild.default_role, overwrite=CHANNEL_PERMS.FORBIDDEN)

         async with self.flux.CONFIG.writeable_conf(ctx.msg_ctx) as cfg:
            channel_dict = cfg.get("channels", {})
            channel_dict[text_channel.id] = [member.id for member in members]
            cfg["channels"] = channel_dict

         await text_channel.send((
            "Thanks for creating the room. Only you and the other user(s) that you created the room with will be able to see this\n"
            "Moderators and Admins will not be able to see this, unless it has been reported.\n"
            "To report an issue with this chatroom (ie: they are aggressive, or mean, etc.) then please type `..report`\n"
            "That will lock the room to prevent message deletion, and eject all users.\n"
            "It will also open the room up to admins and moderators to review the chat, and take appropriate actions as needed.\n"
            "When you are done with the room, type `..leave` to leave the room.")
         )

         return Response(f"Created! {text_channel.mention}\n"
                         f"{', '.join(member.mention for member in members)}")

      @self._commandeer(name="chatmod", default_auths=[aurflux.auth.Record.allow_all()])
      async def _(ctx: aurflux.ty.GuildCommandCtx, _):
         """
         chatmod
         ==
         Creates a chat room with the mods
         ==
         ==
         :param ctx:
         :param _:
         :return:
         """

         overwrites_dict = {**overwrites_base(ctx.msg_ctx.guild), **{ctx.msg_ctx.author: CHANNEL_PERMS.USER}, **get_moderator_overwrite(ctx.msg_ctx.guild)}

         text_channel = await ctx.msg_ctx.guild.create_text_channel(
            name=f"modchat-{ctx.msg_ctx.author.name}",
            category=None,  # todo: add category?
            overwrites=overwrites_dict
         )
         await text_channel.send(
            ("Thanks for creating the room!\n"
             " If you are reporting a user - please provide screenshots and their full Discord username and/or user IDs.\n"
             "If you are reporting an issue within the server -  please provide screenshots and all involved users too.\n"
             ", ".join([r.mention for r in get_moderator_overwrite(ctx.msg_ctx.guild).keys()]))
         )

         return Response(f"Created! {text_channel.mention}\n")

      @self._commandeer(name="report", default_auths=[aurflux.auth.Record.allow_all()])
      async def _(ctx: aurflux.ty.GuildCommandCtx, _):
         """
         report
         ==
         Kicks everyone out of the channel and opens it up for moderator inspection
         ==
         ==
         :param ctx:
         :return:
         """
         await lock_room(ctx.msg_ctx.channel, allow_moderators=True)
         return Response(f"Locking channel! {', '.join([mod.mention for mod in get_moderator_overwrite(ctx.msg_ctx.guild).keys()])}")

      def num_overwrites(channel: discord.TextChannel, me: discord.Member):
         return len([t for t in channel.overwrites if isinstance(t, discord.Member) and t != me])

      @self._commandeer(name="leave", default_auths=[aurflux.auth.Record.allow_all()])
      async def _(ctx: aurflux.ty.GuildCommandCtx, _):
         """
         leave
         ==
         Leaves the channel
         ==
         ==
         :param ctx:
         :return:
         """
         aurconf = self.flux.CONFIG
         async with aurconf.writeable_conf(ctx.msg_ctx) as cfg:
           if "channels" not in cfg:
             cfg["channels"] = {}

         if "channels" not in aurconf.of(ctx.msg_ctx) or ctx.msg_ctx.channel.id not in aurconf.of(ctx.msg_ctx)["channels"]:
            overwrites = ctx.msg_ctx.channel.overwrites
            if not (ctx.msg_ctx.guild.me in overwrites and overwrites[ctx.msg_ctx.guild.default_role].read_messages is False):
               return Response("This can only be used in a roombot channel!", status="error")

         await ctx.msg_ctx.channel.set_permissions(ctx.author_ctx.author, overwrite=None)

         member_overwrites = num_overwrites(ctx.msg_ctx.channel, ctx.msg_ctx.guild.me)

         if member_overwrites == 0:
            await ctx.msg_ctx.channel.delete()
            async with aurconf.writeable_conf(ctx.msg_ctx) as cfg:
               del cfg["channels"][ctx.msg_ctx.channel.id]
         else:
            if member_overwrites == 1:
               await ctx.msg_ctx.channel.edit(reason="Users have dropped down to 1 in channel",
                                              topic=str_2_base64(datetime.utcnow().isoformat()))
            async with aurconf.writeable_conf(ctx.msg_ctx) as cfg:
               cfg["channels"][ctx.msg_ctx.channel.id] = cfg["channels"][ctx.msg_ctx.channel.id].remove(ctx.author_ctx.author.id)
            return Response(f"{ctx.author_ctx.author.mention} has exited the channel")

      @self.router.listen_for(":tock")
      async def clean_up_channels(ev: aurflux.FluxEvent):
         logger.info(self.flux.guilds)
         for guild in self.flux.guilds:
            guild: discord.Guild
            configs = self.flux.CONFIG.of(aurflux.context.ManualGuildCtx(self.flux, guild=guild))
            logger.info(f"{guild} {configs}")
            if "channels" not in configs:
               continue
            for channel, c_id in [(self.flux.get_channel(c), c) for c in configs["channels"]]:
               logger.info(f"Inspecting {channel}")
               if channel and ((topic := channel.topic) and
                               datetime.utcnow() - datetime.fromisoformat(base64_2_str(topic)) > timedelta(days=1)):
                  await channel.delete(reason="24 hours since room dropped to 1 user")
               elif channel and num_overwrites(channel, channel.guild.me) == 0:
                  await channel.delete(reason="Cleanup: No members remaining. Something broke")
               elif channel is None:
                  async with self.flux.CONFIG.writeable_conf(guild.id) as cfg:
                     cfg["channels"].remove(c_id)
