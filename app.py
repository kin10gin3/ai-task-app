import os
import re
import json
import sqlite3
from flask import Flask, request, redirect, render_template, jsonify
from openai import OpenAI

# ====== 基本設定 ======
app = Flask(__name__)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
DB_PATH = "tasks.db"

# ====== DB 初期化 ======
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS tasks(
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 content TEXT NOT NULL,
                 due_date TEXT,
                 priority TEXT
            )"""
        )
        conn.commit()

init_db()

# ====== AIで期限・優先度を判定 ======
def analyze_task(text: str) -> dict:
    prompt = f"""
あなたはタスク管理アシスタントです。与えられたタスク文から以下を日本語で推定し、必ずJSONのみを返してください。
- 期限: YYYY-MM-DD または "不明"
- 優先度: "高" | "中" | "低"

タスク: {text}

出力例:
{{"期限":"2025-08-10","優先度":"高"}}
"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    raw = resp.choices[0].message.content.strip()

    # コードフェンス除去
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()

    try:
        data = json.loads(raw)
    except Exception:
        # フォールバック
        data = {"期限": "不明", "優先度": "中"}
    return {
        "due_date": data.get("期限", "不明"),
        "priority": data.get("優先度", "中")
    }

# ====== ルーティング ======
@app.route("/", methods=["GET"])
def index():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, content, due_date, priority FROM tasks ORDER BY id DESC")
        tasks = c.fetchall()
    return render_template("index.html", tasks=tasks)

@app.route("/add", methods=["POST"])
def add():
    content = request.form.get("content", "").strip()
    if not content:
        return redirect("/")

    ai = analyze_task(content)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO tasks(content, due_date, priority) VALUES(?,?,?)",
            (content, ai["due_date"], ai["priority"]),
        )
        conn.commit()
    return redirect("/")

# API（任意：外部から使いたい場合）
@app.route("/api/tasks", methods=["GET"])
def api_tasks():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, content, due_date, priority FROM tasks ORDER BY id DESC")
        rows = c.fetchall()
    tasks = [{"id": r[0], "content": r[1], "due_date": r[2], "priority": r[3]} for r in rows]
    return jsonify(tasks)

# 動作確認用
@app.route("/ask", methods=["POST"])
def ask():
    q = (request.get_json() or {}).get("question", "")
    if not q:
        return jsonify({"error": "No question provided"}), 400
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": q}],
        temperature=0.2,
    )
    return jsonify({"answer": resp.choices[0].message.content})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
