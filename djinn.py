#!/usr/bin/env python

# This is djinn: A stupid IRC bot written at GenieDB.
# Copyright (C) 2009 Andy Bennett <andyjpb@geniedb.com>
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

import sys
import socket
import string
import time

import re

import urllib


HOST="localhost"
PORT=6667
NICK="djinn"
IDENT="djinn"
REALNAME="Geniebot"
CHAN="#geniedb"

TRAC_TICKETS="http://aladdin.example.net/trac/xos/ticket"

DBG=0
DELAY=0.1
DELAY_INCR=0.1



def send(msg, DBG=0):
    try:
        s.send(msg)
        if DBG:
            print("TX: %s" % msg)
        time.sleep(DELAY)
    except socket.error, emsg:
        return


def privmsg(chan, msg, DBG=0):
    send("PRIVMSG %s :%s\r\n" % (chan, msg), DBG)
    return


def join(chan, DBG=0):
    send("JOIN :%s\r\n" % chan, DBG)


def connect():
    global s
    s=socket.socket( )
    s.connect((HOST, PORT))
    send("NICK %s\r\n" % NICK)
    send("USER %s %s bla :%s\r\n" % (IDENT, HOST, REALNAME))


def pong(SENDER, DATA, CMD = None):
    send("PONG %s\r\n" % SENDER, DBG)


def resolve_tickets(CNL, hits):
    for h in hits:
        h = h.replace(",", " ")
        for i in h.split():
            URL="%s/%s" % (TRAC_TICKETS, i)
            sock = urllib.urlopen("%s" % URL)
            ticket_html = sock.read()
            sock.close()
            ticket_html = ticket_html.replace("\n", "")
            #ticket_title = re.search(r"<title>.*\((.*).*\).*</title>", ticket_html)
            ticket_title = ticket_html.split("<title>")[1].split("</title>")[0]
            ticket_title = re.search(r".*\((.*).*\).*", ticket_title)
            if (ticket_title):
                ticket_title = ticket_title.group(1)
                privmsg(CNL, "Ticket #%s: %s (%s)" % (i, ticket_title, URL))

privmsg_dispatch = {
        r"#(\d+)": resolve_tickets,
        r"tickets? ([\d,\s]*)": resolve_tickets,
        }

def parse_privmsg(SENDER, DATA, CMD = None):
    CNL=DATA[0]
    MSG=DATA[1]

    MSG=MSG.lstrip(":")
    MSG=MSG.strip() # Remove leading and trailing whitespace
    if DBG:
        print("%s : %s" % (CNL, MSG))
    for k, v in privmsg_dispatch.iteritems():
        hits = re.findall(k, MSG.lower())
        if (hits):
            v(CNL, hits)
    if DBG:
        print("")


def parse_error(SENDER, DATA, CMD = None):
    global DELAY
    if (CMD=="ERROR"):
        #CMD=ERROR
        #DATA=[Link:, ip (Excess Flood)]
        DELAY+=DELAY_INCR
        time.sleep(5)
        connect()
        join(CHAN)
        privmsg(CHAN, "Now operating with DELAY=%s" % DELAY)
    elif (CMD=="KICK"):
        print ("Kicked: %s, %s, %s" % (SENDER, DATA, CMD))
        #CMD==KICK
        #DATA=[room, other]
        sys.exit(0)





cmd_dispatch = {
        "PING"   : pong,
        "PRIVMSG": parse_privmsg,
        "ERROR"  : parse_error,
        "KICK"   : parse_error,
        }

def parse(line):
    if 0:
        print ("RX: %s" % line)

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


# An iterator that fills its buffer and returns the new, complete lines.
def buffer():
    buf = ""
    while True:
        # Fetch another 1024 bytes into the buffer
        buf = buf+s.recv(1024)

        # Split the buffer by line.
        # If we fetched a partial line it'll end up in the last element of list temp
        lines = string.split(buf, "\n")

        # Store last item back in readbuffer: probably not a whole line
        buf = lines.pop( )

        yield lines



connect()
join(CHAN)

while 1:
    try:
        fetch = buffer().next
        for line in fetch():
            parse(line)
    except socket.error, emsg:
        time.sleep(10)
        connect()
        join(CHAN)

