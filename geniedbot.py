#!/usr/bin/python

# This is djinn: A stupid IRC bot written at GenieDB.
# Copyright (C) 2009 -> 2010 Andy Bennett <andyjpb@geniedb.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# version 2 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.


# #############################################################################
# djinn : GenieDB IRC Bot
#
#  This is djinn, a stupid IRC bot.
#
#  djinn can:
#   ...be extended to respond to arbitrary regexes that it matches.
#   ...join multiple channels on a single IRC server
#   ...announce when people join and leave channels that it has joined
#   ...be extended to handle different IRC commands
#
#  Specifically,
#   ...query trac to resolve the titles and links for GenieDB ticket numbers
#   ...announce the date and time for different cities around the world
#   ...keep quite for 60 seconds when told to or when it detects a GDB
#    backtrace which can contain things that look like GenieDB ticket numbers
#
# Andy Bennett <andyjpb@geniedb.com>
#
# #############################################################################

## Feature Ideas
#   SMS <-> IRC gateway for tech team & jk
#   (test) system monitoring
#   growld integration
#   support channel loggin
#   remember which nicks belong to which customers
#   perms based on presence in #geniedb?
#   geniedb-support member lists
#     Straight member lists on demand
#     "xxx has joied #geniedb-support and nnnn other customers are lurking"
#   Refactor with IRC object / plugin object model
#   Monitor specific customer support channels and, if no staff are in there, ping them if someone talks
#   When all staff leave a support channel set topic to "say 'staff' to attract attention"
#   resolve mysql-plugin@alaric/cpd-idx into a gitweb hyperlink
#   When staff come into #geniedb-support don't alert #geniedb. Give them ops and privmsg them the /names list
#   Keep track of how long customers have been waiting in waiting rooms
#   When everyone arrives in the morning, or it gets to 11:45, ask when lunch will be. Keep a note and remind people. (via nabaztag?)
#   Use the nabaztag api to alert us when the nabaztag / office wifi goes offline
#   Accept invitations into #geniedb-* by geniedb staff
##


import djinn
import re
import time
import urllib       # For TicketPlugin
import subprocess   # For WorldDatePlugin

BotPlugin = djinn.BotPlugin
debug = djinn.debug

class PrivmsgPlugin(BotPlugin):
	def __init__(self):
		BotPlugin.__init__(self)
		self.name = "Privmsg Plugin"

		self.register_msg = self.register_msg.copy()
		self.register_msg["PRIVMSG"] = PrivmsgPlugin.recv_privmsg

	def recv_privmsg(self, irc_msg):
		for k, v in self.privmsg_dispatch.iteritems():
			for body in irc_msg.body:
				body = body.strip()
				print "<%s>" % body
				hits = re.findall(k, body.lower())
				if hits:
					v(self, irc_msg, hits)
		return True

	privmsg_dispatch = {}

class TicketPlugin(PrivmsgPlugin):
	def __init__(self):
		PrivmsgPlugin.__init__(self)
		self.name = "Ticket Plugin"
		self.ticket_timeout = 300
		self.trac_tickets = "http://aladdin.example.net/trac/ticket"

	def resolve_tickets(self, irc_msg, hits):
		for h in hits:
			h = h.replace(",", " ")
			for i in h.split():
				irc_msg.dump()
				if irc_msg.type != "user":
					if self.ticket_mentions.has_key(irc_msg.reply_to):
						if self.ticket_mentions[irc_msg.reply_to].has_key(i):
						   if self.ticket_mentions[irc_msg.reply_to][i] > time.time()-self.ticket_timeout:
							  continue
					self.ticket_mentions[irc_msg.reply_to][i] = time.time()

				URL="%s/%s" % (self.trac_tickets, i)
				sock = urllib.urlopen("%s" % URL)
				ticket_html = sock.read()
				sock.close()
				ticket_html = ticket_html.replace("\n", "")
				#ticket_title = re.search(r"<title>.*\((.*).*\).*</title>", ticket_html)
				ticket_title = ticket_html.split("<title>")[1].split("</title>")[0]
				ticket_title = re.search(r".*#[0-9\s]*\((.*).*\).*", ticket_title)
				if (ticket_title):
					ticket_title = ticket_title.group(1)
					irc_msg.irc_server.privmsg(irc_msg.reply_to, "Ticket #%s: %s (%s)" % (i, ticket_title, URL))
	
	def init_room(self, irc_evt):
		chan = irc_evt.payload
		self.ticket_mentions[chan] = {}

	ticket_mentions = {}

	privmsg_dispatch = {
			r"#(\d+)": resolve_tickets,
			r"tickets? ([\d,\s]*)": resolve_tickets,
			}

	register_evt = {
			"send_join" : init_room,
			}

# A plugin that makes sure we don't say anything for 60 seconds in channels we've been told to "shutup" in.
class QuenchPlugin(PrivmsgPlugin):
	def __init__(self):
		PrivmsgPlugin.__init__(self)
		self.name = "Quench Plugin"

	def shutup_djinn(self, irc_msg, hits):
		if irc_msg.irc_server.nick not in hits:
			return
		debug(self.dbgstr, "meal %s" % hits)
		self.quench[irc_msg.reply_to] = time.time() + 60

	def shush_djinn(self, irc_msg, hits):
		if irc_msg.irc_server.nick not in hits:
			return
		irc_msg.irc_server.privmsg(irc_msg.reply_to, "No!")
		time.sleep(2)
		irc_msg.irc_server.privmsg(irc_msg.reply_to, ("I think you mean \"shutup %s\"" % irc_msg.irc_server.nick))

	def deny(self, irc_evt):
		chan = irc_evt.payload[0]
		if (not self.quench.has_key(chan)) or (time.time() > self.quench[chan]):
			return True
		else:
			debug(self.dbgstr, "Quenching %s" % irc_evt.payload)
			return False

	quench = {};    # The time after which we're allowed to speak in each channel.
	privmsg_dispatch = {
        r"\(gdb\)"     : shutup_djinn,
        r"shutup (\w+)": shutup_djinn,
        r"shush (\w+)" : shush_djinn,
		}
	
	register_evt = {
			"send_privmsg" : deny,
			#"send_join"    : init_room,
			}
	
class WarbotPlugin(PrivmsgPlugin):
	def __init__(self):
		PrivmsgPlugin.__init__(self)
		self.name = "Warbot Plugin"
		self.warbot_nick = "WarBot"
		self.warbot_passwd="password"

		self.register_msg = self.register_msg.copy()
		self.register_msg["251"] = WarbotPlugin.warbot_login
		self.register_msg["482"] = WarbotPlugin.warbot_reqops

	def warbot_reqsu(self, irc_msg, hits):
		if irc_msg.irc_server.ident not in hits:
			return
		irc_msg.irc_server.privmsg("andyjpb", "warbot likes me")
		if (irc_msg.type == "user") and (irc_msg.src_nick == self.warbot_nick):
			# Request chanops in #geniedb-support so we can see people when it's in auditorium mode
			irc_msg.irc_server.privmsg(self.warbot_nick, "su")

	def warbot_login(self, irc_msg):
		# Registration has just completed, so we can now send msgs to WarBot
		# Identify with WarBot
		irc_msg.irc_server.privmsg(self.warbot_nick, ("auth %s %s" % (irc_msg.irc_server.ident, self.warbot_passwd)))
		return True

	def warbot_reqops(self, irc_msg):
		debug(self.dbgstr, "need to request ops for %s" % irc_msg.opts)
		return True


	privmsg_dispatch = {
			(r"welcome, (\w+)"): warbot_reqsu,
			}

class WorldDatePlugin(PrivmsgPlugin):
	def __init__(self):
		PrivmsgPlugin.__init__(self)
		self.name = "World Date Plugin"
		self.wdate_bin = "wdate"

	def world_date(self, irc_msg, hits):
		if hits[0] != "":
			args = [self.wdate_bin] + [hits[0]]
		else:
			args = [self.wdate_bin]

		try:
			a = subprocess.Popen(args, stdout=subprocess.PIPE).communicate()[0]
			for line in a.split("\n"):
				irc_msg.irc_server.privmsg(irc_msg.reply_to, line)
		except OSError, e:
			irc_msg.irc_server.privmsg(irc_msg.reply_to, ("wdate: %s" % e))

	privmsg_dispatch = {
			r"wdate( [A-Za-z/]*)?": world_date,
			}

class TmpOpPlugin(PrivmsgPlugin):
	def __init__(self):
		PrivmsgPlugin.__init__(self)
		self.name = "Tmp Op Plugin"
		self.nick = "andyjpb"
	def opme(self, irc_msg, hits):
		if (irc_msg.type == "user") and (irc_msg.src_nick == self.nick):
			irc_msg.irc_server.irc_setmode("#geniedb-support", "+o %s" % self.nick)
	def fwd_privmsg(self, irc_msg):
		irc_msg.irc_server.privmsg(self.nick, irc_msg.body)
		return True
	privmsg_dispatch = {
			"opme": opme
			}

class TmpDbgPlugin(BotPlugin):
	def __init__(self):
		BotPlugin.__init__(self)
		self.name = "Tmp Dbg Plugin"
		self.nick = "andyjpb"
	def recv_privmsg(self, irc_msg):
		if irc_msg.type != "user":
			return True
		irc_msg.irc_server.privmsg(self.nick, irc_msg.body)
		return True
	register_msg = {
			"PRIVMSG" : recv_privmsg,
			}

class ChannelPlugin(BotPlugin):
	def __init__(self, channel):
		BotPlugin.__init__(self)
		self.name = "Channel Plugin"
		self.channel = channel

		self.register_msg = self.register_msg.copy()
		self.register_msg["251"] = ChannelPlugin.join_channel
	def join_channel(self, irc_msg):
		irc_msg.irc_server.irc_join(self.channel)
		return True

class StaffChannelPlugin(ChannelPlugin):
	def __init__(self, channel):
		ChannelPlugin.__init__(self, channel)
		self.name = "Staff Channel Plugin"

class WaitingRoomPlugin(ChannelPlugin,PrivmsgPlugin):
	def __init__(self, channel, admin_channel):
		ChannelPlugin.__init__(self, channel)
		PrivmsgPlugin.__init__(self)
		self.admin_channel = admin_channel
		self.name = "Waiting Room Plugin"
		self.support_prefix = "geniedb"
		self.clients = {}
		self.unknown_clients = []
		self.support_rooms = []

		self.register_msg = self.register_msg.copy()
		self.register_msg["JOIN"] = WaitingRoomPlugin.parse_join
		self.register_msg["353"] = WaitingRoomPlugin.parse_names
		self.register_msg["MODE"] = WaitingRoomPlugin.parse_mode
		self.register_msg["443"] = WaitingRoomPlugin.parse_onchannel

	def invite_client(self, client, irc_server):
		company = self.clients[client]
		support_chan = "#%s-%s" % (self.support_prefix, company)
		if support_chan not in self.support_rooms:
			self.support_rooms.append(support_chan)
			### TODO: create and register a new SupportRoomPlugin for this new room.
			###       That plugin can manage logging and staff-absence detection
		irc_server.irc_join(support_chan)
		irc_server.irc_invite(client, support_chan)
		irc_server.privmsg(self.admin_channel, "%s is waiting for support. I know they're from %s so I've invited them to join %s" % (client, company, support_chan))

	def parse_join(self, irc_msg):
		if irc_msg.dst == None:
			chan = irc_msg.body[0]
		else:
			chan = irc_msg.dst
		nick = irc_msg.src_nick
		if nick == irc_msg.irc_server.nick:
			return True

		if chan == self.channel:
			# TODO: check that they're not staff (warbot roles)
			irc_msg.irc_server.privmsg(self.admin_channel, "%s has joined %s" % (nick, self.channel))
			if self.clients.has_key(nick):
				self.invite_client(nick, irc_msg.irc_server)
			else:
				self.unknown_clients.append(nick)
		elif chan in self.support_rooms:
				irc_msg.irc_server.privmsg(self.admin_channel, "%s has joined %s" % (nick, chan))
				irc_msg.irc_server.irc_kick(nick, self.channel, "Support session has begun in %s" % chan)

		return True

	def parse_onchannel(self, irc_msg):
		client = irc_msg.opts[0]
		support_channel = irc_msg.opts[1]
		if support_channel not in self.support_rooms:
			return True

		irc_msg.irc_server.privmsg(self.admin_channel, "%s is already waiting in %s" % (client, support_channel))
		irc_msg.irc_server.irc_kick(client, self.channel, "Support session has begun in %s" % support_channel)
		return True

	def parse_names(self, irc_msg):
		chan = irc_msg.opts[1]
		names = irc_msg.body[0].split()
		if (chan != self.channel):
			return True
		#debug(self.dbgstr, "%s contains %s" % (chan, names))
		if ("@%s" % irc_msg.irc_server.nick) in names:
			self.receive_ops(irc_msg)
		return True

	def parse_mode(self, irc_msg):
		chan = irc_msg.dst
		mode = irc_msg.opts[0]
		if len(irc_msg.opts) >= 2:
			nick = irc_msg.opts[1]
		else:
			nick = None
		if (chan != self.channel) or (nick != irc_msg.irc_server.nick):
			return True
		if mode == "+o":
			self.receive_ops(irc_msg)
		return True

	def receive_ops(self, irc_msg):
		debug(self.dbgstr, "Got ops in %s" % self.channel)
		irc_msg.irc_server.irc_setmode(self.channel, "+um")
		irc_msg.irc_server.irc_settopic(self.channel, "Welcome to %s! A member of staff will be with you shortly." % self.channel)


	def remember_client(self, irc_msg, hits):
		debug(self.dbgstr, "%s" % hits)
		# make sure if comes from someone with warbot role geniedb-staff
		irc_msg.dump()
		if irc_msg.body[0].strip() != irc_msg.irc_server.nick:
			return
		for client, company in hits:
			proposed_support_chan = "#%s-%s" % (self.support_prefix, company)
			if proposed_support_chan == self.channel:
				irc_msg.irc_server.privmsg(irc_msg.reply_to, "I can't use %s for support as I'm using is as the waiting room!" % proposed_support_chan)
			else:
				self.clients[client] = company
				irc_msg.irc_server.privmsg(irc_msg.reply_to, "Thanks! I'll remember that %s is from %s" % (client, company))
				if client in self.unknown_clients:
					self.unknown_clients.remove(client)
					self.invite_client(client, irc_msg.irc_server)
	privmsg_dispatch = {
			"^(\w+) is from (\w+)$": remember_client
			}

	#### TODO: Add a WaitingRoom privmsg handler so that we can detect if someone is speaking in a support channel when no staff are around.
	#### Better still, don't bother fixing privmsg multi-handlers. Instead, register a new plugin for each support channel that we create and then add the handler there




warhead = djinn.IRCBot("localhost", "djinn", "djinn", "GenieBot")
warhead.register_plugin(djinn.BasicPlugin())
warhead.register_plugin(QuenchPlugin())
warhead.register_plugin(WarbotPlugin())
warhead.register_plugin(StaffChannelPlugin("#geniedb"))
warhead.register_plugin(WaitingRoomPlugin("#geniedb-support", "#geniedb"))
warhead.register_plugin(TicketPlugin())
warhead.register_plugin(WorldDatePlugin())
while 1:
    warhead.connect()
    warhead.irc_register()
    warhead.listen()
