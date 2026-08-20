"""Deliberately vulnerable snippets used by the dashboard's PR simulator."""

PY_SAMPLE = '''import os
import pickle
import hashlib
import sqlite3
import requests
from flask import Flask, request

app = Flask(__name__)
API_KEY = "sk_live_51H8xQ2LmNpQrStUvWxYz0123"
CACHE = {}


@app.route("/user")
def get_user():
    user_id = request.args.get("id")
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = '%s'" % user_id)
    row = cur.fetchone()
    CACHE[user_id] = row
    return {"user": row}


@app.route("/ping")
def ping():
    host = request.args.get("host")
    os.system("ping -c 1 " + host)
    return "sent"


@app.route("/restore", methods=["POST"])
def restore():
    blob = request.get_data()
    state = pickle.loads(blob)
    return {"restored": len(state)}


def token_for(email):
    return hashlib.md5(email.encode()).hexdigest()


def fetch_profile(url):
    try:
        return requests.get(url, verify=False, timeout=5).json()
    except Exception:
        pass


def load_config(path):
    data = open(path).read()
    return eval(data)
'''

JS_SAMPLE = '''const express = require("express");
const { exec } = require("child_process");
const crypto = require("crypto");

const app = express();
const JWT_SECRET = process.env.JWT_SECRET || "super-secret-dev-key-123";
const sessions = {};

app.get("/render", (req, res) => {
  const el = document.getElementById("out");
  el.innerHTML = req.query.html;
  res.end();
});

app.get("/ls", (req, res) => {
  exec("ls " + req.query.dir, (err, stdout) => {
    res.send(stdout);
  });
});

app.post("/run", (req, res) => {
  const result = eval(req.body.expression);
  res.json({ result });
});

function sessionId(user) {
  return crypto.createHash("md5").update(user + Math.random()).digest("hex");
}

function track(user) {
  sessions[user.id] = user;
  setInterval(() => {
    fetch("/heartbeat/" + user.id);
  }, 1000);
  window.addEventListener("resize", () => console.log(user.id));
}

function parse(raw) {
  try {
    return JSON.parse(raw);
  } catch (e) {}
}

module.exports = { app, sessionId, track, parse, JWT_SECRET };
'''

SAMPLES = [
    {
        "id": "python-flask",
        "label": "Python / Flask - injection, RCE, weak crypto",
        "file_path": "services/user_api.py",
        "content": PY_SAMPLE,
    },
    {
        "id": "node-express",
        "label": "Node / Express - XSS, command injection, timer leak",
        "file_path": "server/routes.js",
        "content": JS_SAMPLE,
    },
]
