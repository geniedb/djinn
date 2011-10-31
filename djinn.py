#!/usr/bin/env python

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

import socket
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
    print ("%s: %s" % (dbgstr, msg))


class IRCMsg:
    def __init__(self, ircserver, irc_cmd, src, dst, opts, body):
        self.ircserver = ircserver  # Originating IRCServer Object
        self.irc_cmd = irc_cmd      # IRC command (251, 004, PRIVMSG, etc)
        self.src = src              # Sender of the message (user nick & ident, channel, servername)
        self.src_ident = None       # Only for "personal" (user) messages
        self.src_nick = None        # Only for "personal" (user) messages
        self.src_type = None        # server, channel or user
        self.dst = dst              # Recipient of the message (our nick, channel)
        self.opts = opts
        self.body = body            # String or array of body parts
        self.reply_to = None

        self.dbgstr = ircserver.dbgstr + ":IRCMsg"

        pling = src.find("!")
        if (src[0] == "#"):
            self.src_type = "channel"
            self.reply_to = src
        elif (pling >= 0):
            self.src_nick = src[0:pling]
            self.src_ident = src[(pling+1):]
            self.reply_to = self.src_nick
            self.src_type = "user"
        else:
            self.src_type = "server"
            self.reply_to = None
        #debug(self.dbgstr, "     src: <%s>, type: <%s>, reply_to: <%s>, src_ident: <%s>, src_nick: <%s>" % (self.src, self.src_type, self.reply_to, self.src_ident, self.src_nick))


class BotPlugin:
    def __init__(self):
        self.name = None

    register_msg = {}
    register_evt = {}


class IRCServer:
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
        self.pong = None    # The ID of the outstanding PONG we're expecting from the server
        self.socket = None
        self.delay = 0.1
        self.delay_incr = 0.1
        self.rxbuf = None
        self.msg_dispatch = {}
        self.evt_dispatch = {}

    # ###############
    # API
    # ###############
    def connect(self):
        if self.connected == 0:
            debug(self.dbgstr, "Connecting...")
            self.socket = socket.socket()
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
            self.socket.settimeout(self.ping_period)
            self.rxbuf = buffer(self.socket)
            debug(self.dbgstr, "Connected!")
        else:
            debug(self.dbgstr, "Already Connected!")

    # If this function returns then the connection will need to be reestablished
    def listen(self):
        if not self.connected:
            debug(self.dbgstr, "listen(): Not connected!")
            return
        while 1:
            event = None
            try:
                for line in self.rxbuf.next():
                    debug(self.dbgstr, "RX: %s" % line)
                    self.irc_parse(line)
            except socket.timeout, emsg:
                debug(self.dbgstr, "listen(): %s" % emsg)
                event = "socket_timeout"
            except socket.error, emsg:
                debug(self.dbgstr, "listen(): %s" % emsg)
                event = "socket_error"
            if (event != None):
                if (self.evt_dispatch.has_key(event)):
                    for plugin, handler in self.evt_dispatch(event):    # Turn into map?
                        debug(self.dbgstr, "    Handled: %s" % plugin.name)
                        if not handler(plugin, event):
                            self.dropconnect()
                            return
                else:
                    self.dropconnect()
                    return

    def irc_register(self):
            self.send("USER %s %s bla :%s" % (self.ident, self.server, self.realname))
            self.irc_nick()

    def register_plugin(self, plugin):
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

    # ###############
    # IRC Commands
    # ###############
    def irc_nick(self):
        self.send("NICK %s" % self.prefnick)

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
                irc_cmd = meta[1]
                src = meta[0]
                dst = meta[2]
                irc_msg = IRCMsg(self, irc_cmd, src, dst, vars, body)
                #debug(self.dbgstr, "    meta: <%s>, vars: <%s>, body: <%s>" % (meta, vars, body))
            elif (len(line) == 2):     # "PING :irc.local"
                irc_cmd = line[0]
                body = line[1]
                irc_msg = IRCMsg(self, irc_cmd, None, None, None, body)
                debug(self.dbgstr, "    cmd: <%s>, body: <%s>" % (cmd, body))
            else:
                print ("    Can't parse: <%s>" % line)
                raise error
        else:
            debug(self.dbgstr, "irc_parse(): received blank line from server.")

        if (irc_msg != None) and (self.msg_dispatch.has_key(irc_msg.irc_cmd)):
            for plugin, handler in self.msg_dispatch[irc_msg.irc_cmd]:
                debug(self.dbgstr, "    Handled: %s" % plugin.name)
                handler(plugin, irc_msg)
        else:
            debug(self.dbgstr, "    Unhandled command: %s" % irc_cmd)



#warhead = IRCServer("localhost", "djinn2", "djinnv2", "GenieBot")
#while 1:
#    warhead.connect()
#    warhead.irc_register()
#    warhead.listen()

#Pong code
 #                if self.pong == None:
 #                   self.irc_ping()
 #               else:
 #                   debug(self.dbgstr, "Server has gone away!")
 #                   self.ping_period = int(self.ping_period / 2)
 #                   self.dropconnect()
 #                   return


#def irc_ping(self, token = int(time.time())):
#        if self.pong != 0:
#            debug(self.dbgstr, "irc_ping(): Already have a ping outstanding! (%s)" % self.pong)
#        self.pong = str(token)
#        self.send("PING %s" % token)


