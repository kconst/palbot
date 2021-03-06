import discord
import asyncio
import importlib.util
import os
import logging, logging.handlers
import configparser
import re
from collections import deque


FORMAT = "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s"
logging.basicConfig(filename='debug.log',level=logging.DEBUG, format=FORMAT)
client = discord.Client()
logger = logging.getLogger("py3")
client.logger = logger
client.lastresponses= deque(((0,0), (0,0)), maxlen=10)

urlregex = re.compile(r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>])*\))+(?:\(([^\s()<>])*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))")

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')

@client.event
async def on_message(message):
    e = process_message(message)

    if e.output:
        if not e.allowembed:
            e.output = re.sub(urlregex, "<\g<0>>",  e.output)
        respid = await client.send_message(message.channel, e.output)
        client.lastresponses.append((message.id, respid))


@client.event
async def on_message_delete(message):
    for responseto, response in client.lastresponses:
        if message.id == responseto:
            await client.delete_message(response)
            
            
@client.event
async def on_message_edit(before, after):
    for responseto, response in client.lastresponses:
        if before.id == responseto:
            e = process_message(after)
            if e.output:
                if not e.allowembed:
                    e.output = re.sub(urlregex, "<\g<0>>",  e.output)
                await client.edit_message(response, e.output)
            else:
                await client.delete_message(response)
            
            
def process_message(message):
    command = message.content.split(" ")[0].lower()
    args = message.content[len(command) + 1:].strip()
    nick = message.author.name
    e = botEvent(message.channel, nick, str(message.author), args, message)
    e.botnick = client.user.name
    e.allowembed = False
    if command in client.bangcommands:
        client.bangcommands[command](client, e)

    elif command in client.admincommands and\
             str(message.author) in client.botadmins and\
             message.channel.is_private:
        e.output = client.admincommands[command](message.content,
                                                 nick,
                                                 client,
                                                 message)
    
    #lineparsers should be modified to append if necessary instead of clobber
    e.input = message.content
    for command in client.lineparsers:
        command(client, e)
    return e

async def bot_alerts():
    while not client.is_closed:
        logger.debug("Loop of alerts")
        await client.wait_until_ready()
        for alert in client.botalerts:
            if alert.__name__ in client.alertsubs:
                out = alert(client)
                logger.debug("potential alert: {}".format(out))
                if out and not client.is_closed:
                    out = re.sub(urlregex, "<\g<0>>", out)
                    for chid in client.alertsubs[alert.__name__]:
                        channel = discord.Object(id=chid)
                        await client.send_message(channel, out)
                        logger.debug("channel: {} - Alert {}".format(channel, out))
        await asyncio.sleep(60)
    logger.error("apparently the client is closed so I'm killing the alert loop?")


def loadmodules():
    tools_spec = importlib.util.spec_from_file_location("tools", "./botmodules/tools.py")
    client.tools = importlib.util.module_from_spec(tools_spec)
    tools_spec.loader.exec_module(client.tools)
    try:
        client.tools.__init__(client)
        client.tools = vars(client.tools)
    except:
        logger.exception("Could not initialize tools.py:")


    client.bangcommands = {}
    client.admincommands = {}
    client.lineparsers = []
    client.botalerts = []

    filenames = []
    for fn in os.listdir('./botmodules'):
        if fn.endswith('.py') and not fn.startswith('_') and fn.find("tools.py") == -1:
            filenames.append(os.path.join('./botmodules', fn))

    for filename in filenames:
        name = os.path.basename(filename)[:-3]
        try:
            spec = importlib.util.spec_from_file_location(name, filename)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:
            logger.exception("Error loading module: {} Exception:".format(name))
        else:
            try:
                vars(module)['__init__'](client)
            except:
                pass
            for name, func in vars(module).items():
                if hasattr(func, 'command'):
                    command = str(func.command)
                    client.bangcommands[command] = func
                elif hasattr(func, 'admincommand'):
                    command = str(func.admincommand)
                    client.admincommands[command] = func
                elif hasattr(func, 'alert'):
                    client.botalerts.append(func)
                elif hasattr(func, 'lineparser'):
                    if func.lineparser:
                        client.lineparsers.append(func)

    if client.bangcommands:
        commands = 'Loaded command modules: %s' % list(
            client.bangcommands.keys())
    else:
        commands = "No command modules loaded!"

    if client.botalerts:
        botalerts = 'Loaded alerts: %s' % ', '.join(
            (command.__name__ for command in client.botalerts))
    if client.lineparsers:
        lineparsers = 'Loaded line parsers: %s' % ', '.join(
            (command.__name__ for command in client.lineparsers))
    if client.admincommands:
        admincommands = 'Loaded admin commands: %s' % list(
            client.admincommands.keys())
    out = commands + "\n" + botalerts + "\n" + lineparsers + "\n" + admincommands
    logger.info(out)
    return out


def load_config():
    config = configparser.ConfigParser()
    try:
        cfgfile = open('palbot.cfg')
    except IOError:
        logger.logging.exception("You need to create a .cfg file using the example")
        sys.exit(1)

    config.read_file(cfgfile)
    client.botconfig = config
    client.botadmins = config["discord"]["botadmins"].split(",")

    logger.info("Bot admins: {}".format(client.botadmins))


    #alert subscriptions testing
    client.alertsubs = {}
    if config.has_section("alerts"):
        for alert in config["alerts"]:
            client.alertsubs[alert] = set(config["alerts"][alert].split(","))
            client.alertsubs[alert].discard("")

    logger.info("channel alerts: {}".format(client.alertsubs)) 
    #self.error_log = simpleLogger(config['misc']['error_log'])
    #self.event_log = simpleLogger(config['misc']['event_log'])


class botEvent:
    def __init__(self, source, nick, hostmask, inpt, message, output="", notice=False):
        self.source = source
        self.nick = nick
        self.input = inpt
        self.output = output
        self.notice = notice
        self.hostmask = hostmask
        self.message = message

client.loadmodules = loadmodules
client.load_config = load_config
load_config()
loadmodules()
client.loop.create_task(bot_alerts())
client.run(client.botconfig['discord']['token'])
