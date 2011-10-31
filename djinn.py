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
#   ...keep quite for 
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


import sys
import socket
import string
import time

import re

import urllib

import subprocess   # For world_date()


HOST="localhost"
PORT=6667
PREF_NICK="djinn"
IDENT="djinn"
REALNAME="Geniebot"
WARBOT_NICK="WarBot"
WARBOT_PASSWD="password"
ADMIN_CHAN="#geniedb"    # Announce to this channel when people join and leave other channels that we have joined.
WAITING_CHANS=["#geniedb-support"]  # Channels that are +um (auditorium, moderated) where we hold customers and invite them to specfic support channels

TRAC_TICKETS="http://aladdin.example.net/trac/ticket"

DBG=0
DELAY=0.1
DELAY_INCR=0.1

LAST_PING=0
PING_PERIOD=90  # Expect to see a ping from a server every 90 seconds by default
PONG=0    # The ID of the outstanding PONG we're expecting from the server
NICK=PREF_NICK

TICKET_TIMEOUT=300

# Hash of ticket numbers to the time() at which we last
# mentioned that ticket.
ticket_mentions = {}

# The time after which we're allowed to speak in each channel.
quench = {};

CHANS=[]


# #############################################################################
# Wire handlers (transmitters)
#
#  Send messages to the server
#
#  Functions to abstract different functions that we can perform on the server
#
# #############################################################################


def send(msg, DBG=DBG):
    try:
        s.send(msg)
        if DBG:
            print("TX: %s" % msg)
        time.sleep(DELAY)
    except socket.error, emsg:
        return


def privmsg(chan, msg, DBG=DBG):
    if (not quench.has_key(chan)) or (time.time() > quench[chan]):
        send("PRIVMSG %s :%s\r\n" % (chan, msg), DBG)
    return


def setmode(chan, mode, DBG=DBG):
    send("MODE %s %s\r\n" % (chan, mode), DBG)
    return


def settopic(chan, mode, DBG=DBG):
    send("TOPIC %s :%s\r\n" % (chan, mode), DBG)
    return


def warbot_login(action):
    global WARBOT_NICK

    if action == "auth":
        # Identify with WarBot
        privmsg(WARBOT_NICK, ("auth %s %s" % (IDENT, WARBOT_PASSWD)))

    elif action == "su":
        # Request chanops in #geniedb-support so we can see people when it's in auditorium mode
        privmsg(WARBOT_NICK, "su")

    # Write an irc handler that triggers when we get ops
    # The handler should see if we were given ops in a WAITING_CHAN and, if so,
    # set the auditorium and moderated bits on the channel


def join(chan="", DBG=DBG):
    if chan == "":
        warbot_login("auth")
        for chan in CHANS:
            join(chan, DBG)
    else:
        ticket_mentions[chan] = {}
        send("JOIN :%s\r\n" % chan, DBG)


def connect():
    global s
    global PING_PERIOD

    s = socket.socket( )
    s.settimeout(3)
    connected = 0
    while not connected:
        try:
            s.connect((HOST, PORT))
            connected = 1
        except socket.timeout, emsg:
            continue
        except socket.error, emsg:
            time.sleep(5)
            continue
    s.settimeout(PING_PERIOD)
    send("USER %s %s bla :%s\r\n" % (IDENT, HOST, REALNAME))

def nick(NICK=PREF_NICK):
    send("NICK %s\r\n" % NICK)

def check_nick():
    global NICK
    global PREF_NICK

    if NICK != PREF_NICK:
        nick(PREF_NICK)


# #############################################################################


# #############################################################################
# PRIVMSG handlers
#
#  Add a regex to privmsg_dispatch and write a function that handles it.
#
#  When someone says something that matches the regex then the function will be
#   called.
#
# #############################################################################


def resolve_tickets(CNL, hits, personal):
    if (CNL != ADMIN_CHAN):
        return
    for h in hits:
        h = h.replace(",", " ")
        for i in h.split():
            if not personal:
                if ticket_mentions.has_key(CNL):
                    if ticket_mentions[CNL].has_key(i):
                       if ticket_mentions[CNL][i] > time.time()-TICKET_TIMEOUT:
                          continue
                ticket_mentions[CNL][i] = time.time()

            URL="%s/%s" % (TRAC_TICKETS, i)
            sock = urllib.urlopen("%s" % URL)
            ticket_html = sock.read()
            sock.close()
            ticket_html = ticket_html.replace("\n", "")
            #ticket_title = re.search(r"<title>.*\((.*).*\).*</title>", ticket_html)
            ticket_title = ticket_html.split("<title>")[1].split("</title>")[0]
            ticket_title = re.search(r".*#[0-9\s]*\((.*).*\).*", ticket_title)
            if (ticket_title):
                ticket_title = ticket_title.group(1)
                privmsg(CNL, "Ticket #%s: %s (%s)" % (i, ticket_title, URL))


def shutup_djinn(CNL, hits, personal):
    quench[CNL] = time.time() + 60
    return


def shush_djinn(CNL, hits, personal):
    privmsg(CNL, "No!")
    time.sleep(2)
    privmsg(CNL, ("I think you mean \"shutup %s\"" % NICK))


def world_date(CNL, hits, personal):
    if hits[0] != "":
        args = ["wdate"] + [hits[0]]
    else:
        args = ["wdate"]

    try:
        a = subprocess.Popen(args, stdout=subprocess.PIPE).communicate()[0]
        for line in a.split("\n"):
            privmsg(CNL, line)
    except OSError, e:
        privmsg(CNL, ("wdate: %s" % e))


def respond_warbot(CNL, hits, personal):
    global WARBOT_NICK

    if personal and (CNL == WARBOT_NICK):
        warbot_login("su")


def opme(CNL, hits, personal):
    if personal:
        setmode("#geniedb-support", "+o andyjpb")


privmsg_dispatch = {
        r"#(\d+)": resolve_tickets,
        r"tickets? ([\d,\s]*)": resolve_tickets,
        (r"shutup %s" % NICK): shutup_djinn,
        (r"shush %s" % NICK): shush_djinn,
        r"\(gdb\)": shutup_djinn,
        r"wdate( [A-Za-z/]*)?": world_date,
        (r"welcome, %s" % IDENT): respond_warbot,
        "opme": opme,
        }


# #############################################################################


# #############################################################################
# IRC Protocol handlers
#
#  Add an IRC command to cmd_dispatch and write a function that handles it.
#
#  When the command is received from the server then the function will be
#   called.
#
# #############################################################################


def send_pong(SENDER, DATA, CMD = None):
    global LAST_PING
    global PING_PERIOD
    global s

    this_ping = time.time()
    PING_PERIOD = this_ping - LAST_PING + 3    # If the server is pinging us then we probably don't need to ping it to keep the connection alive
    LAST_PING = this_ping
    send("PONG %s\r\n" % SENDER, DBG)
    s.settimeout(PING_PERIOD)

    # The server is managing to ping us so the connection might be relatively stable.
    # See if we can reclaim our preferred nick
    check_nick()


# Receiving our timestamp back from the server means that we're still connected
def recv_pong(SENDER, DATA, CMD = None):
    global PONG
    global PING_PERIOD

    ts=DATA[1][1:]

    if ts == PONG:
        PONG = 0
        PING_PERIOD = PING_PERIOD * 1.1    # The server is alive: open out our ping period
        s.settimeout(PING_PERIOD)
    else:
        print ("Ignoring spurious PONG :%s != %s" % (ts, PONG))


def parse_privmsg(SENDER, DATA, CMD = None):
    CNL=DATA[0]
    MSG=DATA[1]

    MSG=MSG.lstrip(":")
    MSG=MSG.strip() # Remove leading and trailing whitespace

    personal = CNL[:len(NICK)] == NICK
    if DBG:
        print("%s : %s" % (CNL, MSG))
        if personal:
            privmsg("andyjpb", MSG)

    if personal:
        reply_to = SENDER.split(":")[1].split("!")[0]
    else:
        reply_to = CNL
    for k, v in privmsg_dispatch.iteritems():
        hits = re.findall(k, MSG.lower())
        if (hits):
            v(reply_to, hits, personal)
    if DBG:
        print("")


def parse_error(SENDER, DATA, CMD = None):
    global DELAY
    #CMD=ERROR
    #DATA=[Link:, ip (Excess Flood)]
    MSG=DATA[1]
    if MSG == "ip (Excess Flood)":
        DELAY+=DELAY_INCR
        time.sleep(5)
        connect()
        nick()
        privmsg(ADMIN_CHAN, "Now operating with DELAY=%s" % DELAY)
    elif MSG == "reconnect too fast.":
        time.sleep(10)
        connect()
        nick()


def parse_kick(SENDER, DATA, CMD = None):
    print ("Kicked: %s, %s, %s" % (SENDER, DATA, CMD))
    data_parsed = DATA[1].split()
    if data_parsed[0] == NICK:
       sys.exit(0)


def parse_nick(SENDER, DATA, CMD = None):
    global NICK
    # See if we have changed our nick successfully
    # We don't care about other people who change their nicks

    if CMD == "433":
        AST=DATA[0]
        MSG=DATA[1]

        if AST == "*":
            if re.findall(("%s :Nickname is already in use." % NICK), MSG):
                NICK = ("%s_" % NICK)
                nick(NICK)
            #else:
                # If we're not yet properly registered then the server should
                # eventually kick us out and we can have another go...
    #elif CMD == "NICK":


def parse_join(SENDER, DATA, CMD = None):
    CHAN=DATA[0]
    SENDER_NICK = SENDER.split(":")[1].split("!")[0]
    if CHAN != (":%s" % ADMIN_CHAN):
        if NICK != SENDER_NICK:
            privmsg(ADMIN_CHAN, ("%s has joined %s" % (SENDER_NICK, CHAN)))


def receive_ops(CNL):
    if DBG:
        print "Got ops in <%s>" % CNL

    # We implement "waiting rooms" by setting the 'u' (auditorium) and 'm' (moderated) bits on the channel
    # This means that non operators cannot see the other non operators in the channel and they cannot talk
    # to each other either.
    # The parse_join() handler will alert staff in ADMIN_CHAN to their arrival and then they can be
    # invited into private support channels.
    if CNL in WAITING_CHANS:
        setmode(CNL, "+um")
        settopic(CNL, "Welcome to %s! A member of staff will be with you shortly." % CNL)


def parse_names(SENDER, DATA, CMD = None):
    # DATA is
    #  ['djinn_', '= #tgeniedb-support :@djinn_']
    cnl = DATA[1].split("=")[1].split(":")[0].strip()
    names = DATA[1].split(":")[1]

    #if DBG:
    #    print "we think the channel is <%s>" % cnl
    #    print "we think the members are <%s>" % names

    if ("@%s" % NICK) in names.split():
        receive_ops(cnl)


def parse_mode(SENDER, DATA, CMD = None):
    cnl = DATA[0]
    mode = DATA[1]
    # Parameters:   <channel> {[+|-]|o|p|s|i|t|n|b|v} [<limit>] [<user>] [<ban mask>]
    print "parse_mode: SENDER <%s>, DATA <%s>, CMD <%s>" % (SENDER, DATA, CMD)

    if mode == ("+o %s" % NICK):
        receive_ops(cnl)


def registration_complete(SENDER, DATA, CMD = None):
    # Some servers only let us join channels once they've finished sending us
    # the results of connect() and nick()
    # Something like this:
    # :irc.local 251 djinn :There are 8 users and 2 invisible on 1 server
    # looks like a good place to detect succesful registraton.

    global NICK

    NICK = DATA[0]
    if DBG:
        print ("Setting nick to <%s>" % NICK)
        print "Joining channels..."
    join()


cmd_dispatch = {
        "PING"   : send_pong,
        "PONG"   : recv_pong,
        "PRIVMSG": parse_privmsg,
        "ERROR"  : parse_error,
        "KICK"   : parse_kick,
        "433"    : parse_nick,
        "NICK"   : parse_nick,
        "JOIN"   : parse_join,
        "251"    : registration_complete,
        "353"    : parse_names,
        "MODE"   : parse_mode,
        }


# #############################################################################


# #############################################################################
# Wire handlers (receivers)
#
#  Receive messages from the server and feed them into the protocol handlers
#
#  Functions to buffer the lines out of the socket and then parse them into
#   basic parts:
#
#  :<SERVER> <IRC_COMMAND> <DATA>
#
# #############################################################################


def parse(line):
    if DBG:
        print ("RX: %s" % line.replace("\r", "@").replace("\n", "%"))

    line=string.rstrip(line)
    line=string.split(line, None, 3)

    # Here's what a line looks like:
    # <sender> <message>
    # if <sender> == "PING"
    #   <message> is ":<server>"
    # else
    #   <sender> is ":nick!~ident@host"
    #   <message> is <command> <rest>
    # if <command> == "PRIVMSG"
    #   <rest> is "<recipient> :<text>"
    #   <recipient> is "#channel" or "nick"

    SENDER=None
    COMMAND=None
    DATA=None

    oline = list(line)
    if line:
        if(line[0][0]!=":"):
            COMMAND=line.pop(0)
            if (len(line) >= 1):
                SENDER=line.pop(0)
            DATA=line
        else:
            SENDER=line.pop(0)
            if (SENDER[0]==':'):     # Check the message came from a user
                COMMAND=line.pop(0)
                DATA=line

        if (cmd_dispatch.has_key(COMMAND)):
            cmd_dispatch.get(COMMAND)(SENDER, DATA, COMMAND)
        else:
            if DBG:
                print (oline)
                time.sleep(0.1)
    else:
        if DBG:
            print "Received blank line from server"


# An iterator that fills its buffer and returns the new, complete lines.
class buffer:
    def __init__(self):
        self.buf = ""
        self.lines = []

    def __iter__(self):
        return self

    def receive(self):
        # Fetch another 1024 bytes into the buffer
        self.buf = self.buf+s.recv(1024)

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



CHANS.append(ADMIN_CHAN)
CHANS = CHANS + WAITING_CHANS
if DBG:
    print "Channel list: %s" % CHANS

connect()
nick()

buf = buffer()
while 1:
    try:
        for line in buf.next():
            parse(line)
    except socket.timeout, emsg:
        print ("Got <%s> from socket" % emsg)
        # The IRC Server might have timed out
        # First try sending it a ping and waiting a couple of seconds for a reply
        # Replies come via the recv_pong() handler
        # Then try reconnecting
        if PONG == 0:
            PONG = str(int(time.time()))
            send("PING %s\r\n" % PONG, DBG)
            s.settimeout(3)
        else:
            print "Server has gone away: reconnecting"
            PING_PERIOD = int(PING_PERIOD / 2)
            PONG = 0
            connect()
            nick()
    except socket.error, emsg:
        print ("Got <%s> from socket" % emsg)
        time.sleep(10)
        connect()
        nick()

