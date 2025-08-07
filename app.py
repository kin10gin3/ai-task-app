import os
import sqlite3
import json
import re
from datetime import date
from flask import Flask, request, redirect, render_template
from dotenv import load_dotenv
from openai import OpenAI

# ===== 初期設定 =====
load_dotenv()
client = OpenAI(api_kefrom flask import Flask, request, jsonify
import openai
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route("/")
def index():
    return "API is running!"

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message")

    if not message:
        return jsonify({"error": "No message provided"}), 400

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": message}
            ]
        )
        reply = response["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
y=os.getenv("OPENAI_API_KEY"))
app = Flask(__name__)
DB_NAME = "tasks.db"

# ===== SQLite 初期化 =====
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS tasks
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      content TEXT,
                      due_date TEXT,
                      priority TEXT)''')
        conn.commit()

init_db()

# ===== AIで期限と優先度を判定する関数 =====
USE_DUMMY = False  # TrueにするとAIを使わず固定値を返す

def analyze_task(task_text):
    if USE_DUMMY:
        return {"due_date": "2025-08-10", "priority": "中"}

    today = date.today().strftime("%Y-%m-%d")  # 今日の日付を取得

    prompt = f"""
    あなたはタスク管理アシスタントです。
    今日の日付は {today} です。

    ユーザーのタスク文章から、
    - 期限（due_date）: 例 2025-08-10 または "unknown"
    - 優先度（priority）: "高", "中", "低"
    をJSON形式で返してください。

    必ず次の形式で返してください：
    {{"due_date": "YYYY-MM-DD", "priority": "高/中/低"}}

    注意：
    - 「明日」「来週」「1か月後」などの表現は今日の日付から計算して正しい未来日付に変換してください
    - コードブロック（```）など余計な記号は付けず、純粋なJSONだけ返してください

    タスク: {task_text}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    answer = response.choices[0].message.content.strip()

    # === デバッグ出力 ===
    print("=== AIの返答 ===")
    print(answer)

    # ```json などが含まれていたら除去
    answer = re.sub(r"^```[a-zA-Z]*", "", answer)
    answer = re.sub(r"```$", "", answer)
    answer = answer.strip()

    try:
        return json.loads(answer)
    except json.JSONDecodeError:
        print("⚠ JSON変換に失敗しました。デフォルトを返します。")
        return {"due_date": "不明", "priority": "中"}

# ===== ルーティング =====
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        content = request.form["content"]
        ai_result = analyze_task(content)
        due = ai_result.get("due_date", "不明")
        priority = ai_result.get("priority", "中")

        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO tasks (content, due_date, priority) VALUES (?, ?, ?)",
                      (content, due, priority))
            conn.commit()

        return redirect("/")

    # タスク一覧を表示
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM tasks")
        tasks = c.fetchall()
    return render_template("index.html", tasks=tasks)

# ===== Flask起動 =====
if __name__ == "__main__":
    app.run(debug=True)
