import asyncio
from datetime import datetime, timedelta
import discord
import aurflux
from aurflux import MessageContext, AurfluxCog
from aurflux.response import Response
from aurflux.argh import arghify, Arg, MemberIDType
import typing as ty
import base64


# noinspection PyPep8Naming
class CHANNEL_PERMS:
    BOT = discord.PermissionOverwrite(
        read_messages=True,
        send_messages=True,
        add_reactions=True, manage_channels=True,
        manage_permissions=True)
    USER = discord.PermissionOverwrite(
        read_messages=True,
        send_messages=True)
    FORBIDDEN = discord.PermissionOverwrite(
        read_messages=False,
        send_messages=False)


def get_moderator_role(guild: discord.Guild) -> discord.Role:
    return next((role for role in guild.roles if role.permissions.manage_guild), None)


def str_2_base64(s: str):
    return base64.urlsafe_b64encode(s.encode("ascii")).decode("ascii")


def base64_2_str(s: str):
    return base64.urlsafe_b64decode(s.encode("ascii")).decode("ascii")


def overwrites_base(guild: discord.Guild):
    return {
        guild.default_role: CHANNEL_PERMS.FORBIDDEN,
        guild.me: CHANNEL_PERMS.BOT
    }


async def lock_room(channel: discord.TextChannel, allow_moderators=False):
    overwrites_dict = overwrites_base(channel.guild)

    overwrites_dict = {**{target: CHANNEL_PERMS.FORBIDDEN for target in channel.members}, **overwrites_dict}

    if allow_moderators:
        overwrites_dict[get_moderator_role(channel.guild)] = CHANNEL_PERMS.USER

    await asyncio.gather(*[
        channel.set_permissions(target, overwrite=overwrite)
        for target, overwrite in overwrites_dict.items()
    ])


class RoomHandler(AurfluxCog):
    last_seen_cache: ty.Dict[discord.TextChannel, discord.Message] = {}

    def route(self):
        @arghify
        @self.aurflux.commandeer(name="chat", parsed=True)
        async def _(ctx: MessageContext, member_ids: Arg(names=("member",), nargs="+", type_=MemberIDType)):
            members = [ctx.guild.get_member(member_id) for member_id in set(member_ids) | {ctx.author.id}]

            if len(members) < 2:
                return Response(f"Please create a room with at least 2 people!", errored=True)

            overwrites_dict = {**overwrites_base(ctx.guild), **{target: CHANNEL_PERMS.USER for target in members}}

            text_channel = await ctx.guild.create_text_channel(
                name="-".join([member.name for member in members]),
                category=None,  # todo: add category?
                overwrites=overwrites_dict
            )
            async with self.aurflux.CONFIG.writeable_conf(ctx) as cfg:
                cfg["channels"][text_channel.id] = [member.id for member in members]

            return Response(f"Created! {text_channel.mention}\n"
                            f"{', '.join(member.mention for member in members)}")

        @self.aurflux.commandeer(name="report", parsed=False)
        async def _(ctx: MessageContext):
            """
            report
            Kicks everyone out of the channel and opens it up for moderator inspection
            :param ctx:
            :return:
            """
            await lock_room(ctx.channel, allow_moderators=True)
            return Response(f"Locking channel! {get_moderator_role(ctx.guild).mention}")

        @self.aurflux.commandeer(name="leave", parsed=False)
        async def _(ctx: MessageContext):
            """
            leave
            Leaves the channel
            :param ctx:
            :param args:
            :return:
            """
            aurconf = self.aurflux.CONFIG
            if ctx.channel.id not in aurconf.of(ctx)["channels"]:
                return Response("This can only be used in a roombot channel!", errored=True)
            await ctx.channel.set_permissions(ctx.author, overwrite=None)

            if len(ctx.channel.overwrites) == 1:
                await ctx.channel.delete()
                async with aurconf.writeable_conf(ctx) as cfg:
                    del cfg["channels"][ctx.channel.id]
            else:
                if len(ctx.channel.overwrites) == 2:
                    await ctx.channel.edit(reason="Users have dropped down to 1 in channel",
                                           topic=str_2_base64(datetime.utcnow().isoformat()))
                async with aurconf.writeable_conf(ctx) as cfg:
                    cfg["channels"][ctx.channel.id] = cfg["channels"][ctx.channel.id].remove(ctx.author.id)
                return Response(f"{ctx.author.mention} has exited the channel")

        @self.router.endpoint("roombot:tock")
        async def clean_up_channels(ev: aurflux.AurfluxEvent):
            for guild in self.aurflux.guilds:
                guild: discord.Guild
                configs = self.aurflux.CONFIG.of(guild.id)
                for channel in [self.aurflux.get_channel(c) for c in configs["channels"]]:
                    if ((topic := channel.topic) and
                            datetime.utcnow() - datetime.fromisoformat(base64_2_str(topic)) > timedelta(days=1)):
                        await channel.delete(reason="24 hours since room dropped to 1 user")
