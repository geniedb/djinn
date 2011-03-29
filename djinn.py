#!/usr/bin/env python

# This is djinn: A stupid IRC bot written at GenieDB.
# Copyright (C) 2009 -> 2011 Andy Bennett <andyjpb@geniedb.com>
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
#  This is djinn, a stupid IRC bot framework.
#
#  djinn can:
#   ...be extended to respond to arbitrary irc commands that it matches.
#   ...be extended to handle different IRC commands
#
# Andy Bennett <andyjpb@geniedb.com>, 2010/08/19
#
# #############################################################################

import socket
import select
import time
import string

# An iterator that fills its buffer and returns the new, complete lines.
class buffer:
    def __init__(self, socket):
        self.buf = ""
        self.lines = []
        self.s = socket

    def __iter__(self):
        return self

    def receive(self):
        # Fetch another 1024 bytes into the buffer
        self.buf = self.buf+self.s.recv(1024)

        # Split the buffer by line.
        # If we fetched a partial line it'll end up in the last element of list temp
        self.lines = string.split(self.buf, "\r\n")

        # Store last item back in readbuffer: probably not a whole line
        self.buf = self.lines.pop( )

    def next(self):
        if len(self.lines) == 0:
            self.receive()
        try:
            line = self.lines.pop(0)
        except:
            raise socket.timeout
        yield line


def debug(dbgstr, msg):
    print ("[%s] %s: %s" % (time.strftime("%a:%H:%M:%S"), dbgstr, msg))


class IRCMsg:
    def __init__(self, ircserver, irc_cmd, src, dst, opts, body):
        self.irc_server = ircserver  # Originating IRCServer Object
        self.irc_cmd = irc_cmd      # IRC command (251, 004, PRIVMSG, etc)
        self.src = src              # Sender of the message (user nick & ident, channel, servername)
        self.src_ident = None       # Only for "personal" (user) messages
        self.src_nick = None        # Only for "personal" (user) messages
        self.type = None            # server, channel or user
        self.dst = dst              # Recipient of the message (our nick, channel)
        self.opts = opts
        self.body = body            # String or array of body parts
        self.reply_to = None

        self.dbgstr = ircserver.dbgstr + ":IRCMsg"

        if src != None:
            pling = src.find("!")
            if (pling >= 0):
                self.src_nick = src[0:pling]
                self.src_ident = src[(pling+1):]
            if (dst != None) and (dst[0] == "#"):
                self.reply_to = dst
                self.type = "channel"
            elif (pling >= 0):
                self.reply_to = self.src_nick
                self.type = "user"
            else:
                self.type = "server"
                self.reply_to = None
            #debug(self.dbgstr, "     src: <%s>, type: <%s>, reply_to: <%s>, src_ident: <%s>, src_nick: <%s>" % (self.src, self.type, self.reply_to, self.src_ident, self.src_nick))
        else:
            self.type = "server"
            self.reply_to = None

    def dump(self):
        print("ircserver : <%s>" % self.irc_server)
        print("  irc_cmd : <%s>" % self.irc_cmd)
        print("      src : <%s>" % self.src)
        print("src_ident : <%s>" % self.src_ident)
        print(" src_nick : <%s>" % self.src_nick)
        print(" type     : <%s>" % self.type)
        print("      dst : <%s>" % self.dst)
        print("     opts : <%s>" % self.opts)
        print("     body : <%s>" % self.body)
        print(" reply_to : <%s>" % self.reply_to)
        print("   dbgstr : <%s>" % self.dbgstr)

class IRCEvt:
    def __init__(self, ircserver, irc_evt, payload):
        self.irc_server = ircserver
        self.irc_evt = irc_evt
        self.payload = payload
        self.dbgstr = ircserver.dbgstr + ":IRCEvt"

    def dump(self):
        print("ircserver : <%s>" % self.irc_server)
        print("  irc_cmd : <%s>" % self.irc_evt)
        for payload in self.payload:
            print("  payload : <%s>" % payload)
        print("   dbgstr : <%s>" % self.dbgstr)


class BotPlugin:
    def __init__(self):
        self.name = None
    def startup(self, irc_server):
        self.dbgstr = ("%s:%s" % (irc_server.dbgstr, self.name))
        debug(self.dbgstr, "Starting")
    register_msg = {}
    register_evt = {}


# Provides basic handlers that deal with ping/pong, nicks, etc
# Does this by pulling in other plugins
class BasicPlugin(BotPlugin):
    def __init__(self):
        BotPlugin.__init__(self)
        self.name = "Basic Plugin"
    def startup(self, irc_server):
        BotPlugin.startup(self, irc_server)
        irc_server.register_plugin(ErrorPlugin())
        irc_server.register_plugin(NickChooserPlugin())
        irc_server.register_plugin(PingPongPlugin())

class ErrorPlugin(BotPlugin):
    def __init__(self):
        BotPlugin.__init__(self)
        self.name = "Error Plugin"
    def handle_error(self, irc_msg):
        if irc_msg.body[0] == "ip (Excess Flood)":
            irc_msg.irc_server.delay += irc_msg.irc_server.delay_incr
            return False    # Cause the connection to be dropped
        if irc_msg.body[0] == "reconnect too fast.":
            time.delay(10)
            return False    # Cause the connection to be dropped
        return True
    register_msg = {
            "ERROR" : handle_error,
            }

class NickChooserPlugin(BotPlugin):
    def __init__(self):
        BotPlugin.__init__(self)
        self.name = "Nick Chooser Plugin"
    def got_nick(self, irc_msg):
        irc_msg.irc_server.nick = irc_msg.dst
        return True
    def nick_in_use(self, irc_msg):
        if irc_msg.body[0] == "Nickname is already in use.":
            new_nick = ("%s_" % irc_msg.irc_server.nick)
            irc_msg.irc_server.nick = new_nick
            irc_msg.irc_server.irc_nick(new_nick)
        return True
    def check_nick(self, irc_msg):
        if irc_msg.irc_server.nick != irc_msg.irc_server.prefnick:
            irc_msg.irc_server.nick = irc_msg.irc_server.prefnick
            irc_msg.irc_server.irc_nick(irc_msg.irc_server.prefnick)
        return True
    register_msg = {
            "251"    : got_nick,
            "433"    : nick_in_use,
            "PING"   : check_nick,
            "PONG"   : check_nick,
            }

class PingPongPlugin(BotPlugin):
    def __init__(self):
        BotPlugin.__init__(self)
        self.name = "Ping/Pong Plugin"
        self.pong = None    # The ID of the outstanding PONG we're expecting from the server
        self.last_ping = 0
        self.ping_period = 90
    def send_pong(self, irc_msg):
        this_ping = time.time()
        self.ping_period = this_ping - self.last_ping + 3    # If the server is pinging us then we probably don't need to ping it to keep the connection alive
        self.last_ping = this_ping
        irc_msg.irc_server.send("PONG %s" % irc_msg.body[0])
        irc_msg.irc_server.timeout = self.ping_period
        return True
    def recv_pong(self, irc_msg):
        ts = irc_msg.body[0]
        if ts == self.pong:
            self.pong = None
            self.ping_period = self.ping_period * 1.1    # The server is alive: open out our ping period
            irc_msg.irc_server.timeout = self.ping_period
        else:
            debug(self.dbgstr, "Ignoring spurious PONG :%s != %s" % (ts, self.pong))
        return True
    def send_ping(self, irc_evt):
        if self.pong == None:
            self.pong = str(int(time.time()))
            irc_evt.irc_server.send("PING %s" % self.pong)
            irc_evt.irc_server.timeout = 3
            return True
        else:
            self.ping_period = int(self.ping_period / 2)
            debug(self.dbgstr, "Won't PING: token already outstanding: %s" % self.pong)
            return False
    register_msg = {
            "PING"   : send_pong,
            "PONG"   : recv_pong,
            }
    register_evt = {
            "socket_timeout" : send_ping,
            }


# Provides handlers that list plugins, etc
class DbgPlugin(BotPlugin):
    def __init__(self):
        BotPlugin.__init__(self)
        self.name = "Debugging Plugin"


class IRCBot:
    def __init__(self, server, ident, nick, realname, port = 6667):
        self.server = server
        self.ident = ident
        self.prefnick = nick
        self.nick = nick
        self.realname = realname
        self.port = port
        self.connected = 0
        self.dbgstr = ("%s:%s" % (server, ident))
        self.ping_period = 90     # Expect to see a ping from a server every 90 seconds by default
        self.socket = None
        self.timeout = 3
        self.poll = None
        self.delay = 0.1
        self.delay_incr = 0.1
        self.rxbuf = None
        self.plugins = []
        self.msg_dispatch = {}
        self.evt_dispatch = {}

    # ###############
    # API
    # ###############
    def connect(self):
        if self.connected == 0:
            debug(self.dbgstr, "Connecting...")
            self.socket = socket.socket()
            self.timeout = 3
            self.socket.settimeout(3)
            while not self.connected:
                try:
                    self.socket.connect((self.server, self.port))
                    self.connected = 1
                except socket.timeout, emsg:
                    debug(self.dbgstr, "Failed connect(): %s" % emsg)
                    continue
                except socket.error, emsg:
                    debug(self.dbgstr, "Failed connect(): %s" % emsg)
                    time.sleep(5)
                    continue
            self.timeout = self.ping_period
            self.socket.settimeout(0.0)
            self.socket.setblocking(0)
            self.poll = select.poll()
            self.poll.register(self.socket, select.POLLIN)
            self.rxbuf = buffer(self.socket)
            debug(self.dbgstr, "Connected!")
            self.fire_evt("connected")
        else:
            debug(self.dbgstr, "Already Connected!")

    # If this function returns then the connection will need to be reestablished
    def listen(self):
        if not self.connected:
            debug(self.dbgstr, "listen(): Not connected!")
            return
        while 1:
            event = None
            payload = None
            poll_events = self.poll.poll(self.timeout * 1000)
            if not poll_events:
                event = "socket_timeout"
            for poll_fd, poll_evt in poll_events:
                if poll_fd == self.socket.fileno():
                    try:
                        while 1:
                            for line in self.rxbuf.next():
                                debug(self.dbgstr, "RX: %s" % line)
                                if not self.irc_parse(line):
                                    self.dropconnect()
                                    return
                    except socket.timeout, emsg:
                        debug(self.dbgstr, "listen(): %s" % emsg)
                        event = "socket_timeout"
                    except socket.error, (eno, emsg):
                        if eno == 11:
                            debug(self.dbgstr, "listen(): nothing to read")
                            #event = "socket_timeout"
                        else:
                            debug(self.dbgstr, "listen(): %s" % emsg)
                            event = "socket_error"
                else:
                    event = "socket"
                    payload = poll_fd, poll_evt
            if (event != None):
                event = self.fire_evt(event, payload)
                if event == "unhandled":
                    debug(self.dbgstr, "    Unhandled socket event: aborting!")
                    self.dropconnect()
                    return
                elif event == "failed":
                    self.dropconnect()
                    return

    def register_plugin(self, plugin):
        self.plugins.append(plugin)
        debug(self.dbgstr, "Registering plugin: %s!" % plugin.name)
        for evt, fn in plugin.register_evt.iteritems():
            debug(self.dbgstr, "    evt: <%s>" % evt)
            if not self.evt_dispatch.has_key(evt):
                self.evt_dispatch[evt] = []
            self.evt_dispatch[evt].append([plugin, fn])
        for msg, fn in plugin.register_msg.iteritems():
            debug(self.dbgstr, "    msg: <%s>" % msg)
            if not self.msg_dispatch.has_key(msg):
                self.msg_dispatch[msg] = []
            self.msg_dispatch[msg].append([plugin, fn])
        plugin.startup(self)

    # ###############
    # IRC Commands
    # ###############
    def irc_register(self):
        self.send("USER %s %s bla :%s" % (self.ident, self.server, self.realname))
        self.irc_nick(self.prefnick)

    def irc_nick(self, nick):
        self.send("NICK %s" % self.nick)

    def privmsg(self, chan, msg):
        event = self.fire_evt("send_privmsg", [chan, msg])
        if event != "failed":    # Noone prevented us from sending the message
            self.send("PRIVMSG %s :%s" % (chan, msg))

    def irc_setmode(self, entity, mode):
        event = self.fire_evt("send_mode", [entity, mode])
        self.send("MODE %s %s" % (entity, mode))

    def irc_join(self, chan):
        event = self.fire_evt("send_join", chan)
        self.send("JOIN :%s" % chan)

    def irc_settopic(self, chan, topic):
        event = self.fire_evt("send_topic", [chan, topic])
        self.send("TOPIC %s :%s" % (chan, topic))

    def irc_invite(self, nick, chan):
        event = self.fire_evt("send_invite", [nick, chan])
        self.send("INVITE %s :%s" % (nick, chan))

    def irc_kick(self, nick, chan, reason=None):
        event = self.fire_evt("send_kick", [nick, chan, reason])
        self.send("KICK %s %s :%s" % (chan, nick, reason))

    # ###############
    # Private
    # ###############

    def send(self, msg):
        try:
            debug(self.dbgstr, "TX: %s" % msg)
            self.socket.send("%s\r\n" % msg)
            time.sleep(self.delay)
        except socket.error, emsg:
            debug(self.dbgstr, "send(): %s" % emsg)

    def dropconnect(self):
        debug(self.dbgstr, "Discarding connection!")
        self.socket = None
        self.rxbuf = None
        self.connected = 0
        time.sleep(10)

    def irc_parse(self, line):
        line = string.rstrip(line)
        line = string.split(line, ":")

        irc_msg = None
        if line:
            if (len(line[0]) == 0):    # ":sender code recipient :body"
                tmp = line[1].rstrip().split()
                meta = tmp[0:3]
                vars = tmp[3:]
                if (len(line) >= 3):   # ":sender code recipient :body :body"
                    body = line[2:]
                elif (len(line) == 2): # ":sender code recipient"
                    body = None
                else:
                    print ("    Can't parse: <%s>" % line)
                    raise error
                irc_cmd = meta[1].strip()
                src = meta[0]
                if len(meta) > 2:
                    dst = meta[2]
                else:
                    dst = None
                irc_msg = IRCMsg(self, irc_cmd, src, dst, vars, body)
                #debug(self.dbgstr, "    meta: <%s>, vars: <%s>, body: <%s>" % (meta, vars, body))
            elif (len(line) >= 2):     # "PING :irc.local" or "ERROR :Closing link (djinn2@127.0.0.1) [Ping timeout: 121 seconds]"
                irc_cmd = line[0].strip()
                body = line[1:]
                irc_msg = IRCMsg(self, irc_cmd, None, None, None, body)
                debug(self.dbgstr, "    cmd: <%s>, body: <%s>" % (irc_cmd, body))
            else:
                print ("    Can't parse: <%s>" % line)
                raise error
        else:
            debug(self.dbgstr, "irc_parse(): received blank line from server.")

        if (irc_msg != None) and (self.msg_dispatch.has_key(irc_msg.irc_cmd)):
            for plugin, handler in self.msg_dispatch[irc_msg.irc_cmd]:
                debug(self.dbgstr, "    Handled: %s" % plugin.name)
                if not handler(plugin, irc_msg):
                    print "being false"
                    return False
        return True

    # returns
    #  "unhandled" if noone handled the event
    #  "failed" if a handler returned False
    #  or "success" if all the handlers returned True
    def fire_evt(self, event, payload=None):
        state = "unhandled"
        if (self.evt_dispatch.has_key(event)):
            state = "success"
            for plugin, handler in self.evt_dispatch[event]:    # Turn into map?
                # If any of the events return False then we must report failure
                result = handler(plugin, IRCEvt(self, event, payload))
                if not result:
                    state = "failed"
                debug(self.dbgstr, "    %s handled: %s (%s)" % (event, plugin.name, result))
                #return state
        return state
