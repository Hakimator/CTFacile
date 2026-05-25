"""
CTFacile — SQL Injection Login Bypass Challenge
-----------------------------------------------
Intentionally vulnerable Flask app for educational CTF use.
Reads FLAG and ADMIN_USERNAME from environment variables injected by DockerManagerService.

Vulnerability: raw string interpolation in SQL → classic login bypass via ' OR '1'='1
"""

import os
import sqlite3
import hashlib
from flask import Flask, request, session, redirect, url_for, render_template_string

app = Flask(__name__)
app.secret_key = os.urandom(24)

FLAG           = os.environ.get("FLAG",           "FLAG{sqli_master}")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "s3cr3t_p4ssw0rd_not_for_you")

DB_PATH = "/tmp/challenge.db"


# ---------------------------------------------------------------------------
# Bootstrap DB on first run
# ---------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            role     TEXT NOT NULL DEFAULT 'user'
        )
    """)
    # Check if admin already seeded
    existing = cur.execute("SELECT 1 FROM users WHERE username = ?", (ADMIN_USERNAME,)).fetchone()
    if not existing:
        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (ADMIN_USERNAME, ADMIN_PASSWORD, "admin"),
        )
    # Decoy users so the table isn't trivially empty
    for name, pw in [("alice", "hunter2"), ("bob", "qwerty123"), ("charlie", "iloveyou")]:
        if not cur.execute("SELECT 1 FROM users WHERE username = ?", (name,)).fetchone():
            cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, 'user')", (name, pw))
    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------------------------
# HTML templates (inline — no template files needed)
# ---------------------------------------------------------------------------
LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CorpNet Login — Secure Access Portal</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #0f172a;
    font-family: 'Segoe UI', system-ui, sans-serif;
    color: #e2e8f0;
  }
  .card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 40px 36px;
    width: 100%;
    max-width: 400px;
    box-shadow: 0 25px 50px -12px rgba(0,0,0,.6);
  }
  .logo {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 28px;
  }
  .logo-mark {
    width: 36px; height: 36px;
    background: rgba(59,130,246,.15);
    border: 1px solid rgba(59,130,246,.3);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
  }
  .logo-mark svg { color: #3b82f6; }
  .logo-text { font-size: 17px; font-weight: 700; letter-spacing: -.3px; }
  .logo-text span { color: #3b82f6; }
  h1 { font-size: 18px; font-weight: 600; margin-bottom: 4px; }
  .subtitle {
    font-size: 12px; color: #64748b; margin-bottom: 28px; font-family: monospace;
  }
  .hint-box {
    background: rgba(59,130,246,.07);
    border: 1px solid rgba(59,130,246,.2);
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 22px;
    font-size: 12px;
    color: #93c5fd;
    font-family: monospace;
    line-height: 1.6;
  }
  .hint-box code {
    background: rgba(255,255,255,.06);
    padding: 1px 5px;
    border-radius: 4px;
    color: #7dd3fc;
  }
  label {
    display: block;
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: .07em;
    color: #94a3b8;
    margin-bottom: 6px;
  }
  input[type=text], input[type=password] {
    width: 100%;
    background: rgba(15,23,42,.6);
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 13px;
    color: #fff;
    font-family: monospace;
    outline: none;
    transition: border-color .15s, box-shadow .15s;
    margin-bottom: 16px;
  }
  input:focus {
    border-color: rgba(59,130,246,.5);
    box-shadow: 0 0 0 3px rgba(59,130,246,.1);
  }
  button[type=submit] {
    width: 100%;
    background: #3b82f6;
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 11px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: background .15s;
    margin-top: 4px;
  }
  button[type=submit]:hover { background: #2563eb; }
  .error {
    background: rgba(239,68,68,.1);
    border: 1px solid rgba(239,68,68,.3);
    color: #fca5a5;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 12px;
    text-align: center;
    margin-bottom: 18px;
    font-family: monospace;
  }
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <div class="logo-mark">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="11" width="18" height="11" rx="2"/>
        <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
      </svg>
    </div>
    <span class="logo-text"><span>Corp</span>Net</span>
  </div>

  <h1>Secure Access Portal</h1>
  <p class="subtitle">Authentication required — authorised personnel only</p>

  <div class="hint-box">
    The login query looks like:<br>
    <code>SELECT * FROM users WHERE username='$u' AND password='$p'</code>
  </div>

  {% if error %}
  <div class="error">{{ error }}</div>
  {% endif %}

  <form method="post" action="/login">
    <label>Username</label>
    <input type="text" name="username" autocomplete="off" autofocus>
    <label>Password</label>
    <input type="password" name="password">
    <button type="submit">Sign In</button>
  </form>
</div>
</body>
</html>
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CorpNet — Admin Dashboard</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    min-height: 100vh;
    background: #0f172a;
    font-family: 'Segoe UI', system-ui, sans-serif;
    color: #e2e8f0;
    padding: 40px 20px;
  }
  .container { max-width: 680px; margin: 0 auto; }
  .topbar {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 32px;
  }
  .logo { display: flex; align-items: center; gap: 10px; }
  .logo-mark {
    width: 32px; height: 32px;
    background: rgba(59,130,246,.15);
    border: 1px solid rgba(59,130,246,.3);
    border-radius: 7px;
    display: flex; align-items: center; justify-content: center;
  }
  .logo-text { font-size: 15px; font-weight: 700; }
  .logo-text span { color: #3b82f6; }
  .badge {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: .08em; padding: 3px 8px; border-radius: 5px;
    background: rgba(245,158,11,.1); border: 1px solid rgba(245,158,11,.3);
    color: #fbbf24; font-family: monospace;
  }
  .welcome {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 28px;
    margin-bottom: 20px;
  }
  .welcome h2 {
    font-size: 15px; font-weight: 600; margin-bottom: 6px; color: #f8fafc;
  }
  .welcome p { font-size: 13px; color: #64748b; }
  .flag-card {
    background: rgba(34,197,94,.05);
    border: 1px solid rgba(34,197,94,.25);
    border-radius: 12px;
    padding: 24px 28px;
  }
  .flag-card .label {
    display: flex; align-items: center; gap-8px;
    font-size: 11px; font-weight: 500; text-transform: uppercase;
    letter-spacing: .1em; color: #4ade80; margin-bottom: 12px;
    gap: 6px;
  }
  .flag-card .label svg { flex-shrink: 0; }
  .flag-value {
    font-family: monospace;
    font-size: 16px;
    font-weight: 700;
    color: #4ade80;
    background: rgba(34,197,94,.07);
    border: 1px solid rgba(34,197,94,.2);
    border-radius: 8px;
    padding: 14px 16px;
    word-break: break-all;
    letter-spacing: .02em;
    user-select: all;
  }
  .flag-hint {
    font-size: 11px; color: #475569; margin-top: 10px; font-family: monospace;
  }
  .logout {
    display: inline-flex; align-items: center; gap: 6px;
    margin-top: 20px;
    font-size: 12px; color: #64748b;
    text-decoration: none; border: 1px solid #1e293b;
    padding: 7px 14px; border-radius: 7px;
    transition: color .15s, border-color .15s;
  }
  .logout:hover { color: #e2e8f0; border-color: #334155; }
</style>
</head>
<body>
<div class="container">
  <div class="topbar">
    <div class="logo">
      <div class="logo-mark">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2"/>
          <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
        </svg>
      </div>
      <span class="logo-text"><span>Corp</span>Net</span>
    </div>
    <span class="badge">Admin</span>
  </div>

  <div class="welcome">
    <h2>Welcome, {{ username }}</h2>
    <p>You have successfully authenticated as an administrator via SQL injection bypass.</p>
  </div>

  <div class="flag-card">
    <div class="label">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
        <line x1="4" x2="4" y1="22" y2="15"/>
      </svg>
      Flag
    </div>
    <div class="flag-value">{{ flag }}</div>
    <p class="flag-hint">Submit this flag in the CTFacile challenge modal to claim your points.</p>
  </div>

  <a href="/logout" class="logout">
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
      <polyline points="16 17 21 12 16 7"/>
      <line x1="21" x2="9" y1="12" y2="12"/>
    </svg>
    Logout
  </a>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    return render_template_string(LOGIN_HTML, error=None)


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "")
    password = request.form.get("password", "")

    # !! INTENTIONALLY VULNERABLE — raw string interpolation !!
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(query)
        row = cur.fetchone()
        conn.close()
    except Exception as e:
        conn.close()
        return render_template_string(
            LOGIN_HTML,
            error=f"DB Error: {e}"
        )

    if row:
        session["logged_in"] = True
        session["username"] = row[1]   # column 1 = username
        return redirect(url_for("dashboard"))

    return render_template_string(LOGIN_HTML, error="Invalid credentials. Access denied.")


@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("index"))
    return render_template_string(
        DASHBOARD_HTML,
        username=session.get("username", "unknown"),
        flag=FLAG,
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
