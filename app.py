from flask import Flask, request, jsonify
from openai import OpenAI
from datetime import datetime, timedelta
import re, json, sqlite3, os

app = Flask(__name__)

# --- DB 設定 ---
DB_PATH = "tasks.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT,
                due_date TEXT,
                priority TEXT
            )"""
        )
        conn.commit()

init_db()

# --- OpenAI クライアント ---
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ============================================================
# 日付正規化用の関数
# ============================================================
def _iso_from_loose_str(s: str) -> str | None:
    """'2025-8-7' など緩い表記→ '2025-08-07' に整形"""
    if not isinstance(s, str):
        return None
    s = s.strip()
    m = re.fullmatch(r"(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return None

def _parse_relative_ja(s: str) -> str | None:
    """日本語の相対表現→ISO日付"""
    if not isinstance(s, str):
        return None
    t = datetime.now().date()
    s = s.strip()

    if s in ("今日", "本日"):
        return t.isoformat()
    if s in ("明日", "あした"):
        return (t + timedelta(days=1)).isoformat()
    if s in ("明後日", "あさって"):
        return (t + timedelta(days=2)).isoformat()
    if s.startswith("来週"):
        return (t + timedelta(days=7)).isoformat()
    if re.fullmatch(r"\d+\s*日後", s):
        n = int(re.findall(r"\d+", s)[0]);  return (t + timedelta(days=n)).isoformat()
    if re.fullmatch(r"\d+\s*週間?後", s):
        n = int(re.findall(r"\d+", s)[0]);  return (t + timedelta(days=7*n)).isoformat()
    if re.fullmatch(r"\d+\s*か月後|\d+\s*ヶ月後|\d+\s*月後", s):
        n = int(re.findall(r"\d+", s)[0]);  return (t + timedelta(days=30*n)).isoformat()
    if s == "来月":
        return (t + timedelta(days=30)).isoformat()

    return None

# ============================================================
# タスク解析 (AI 呼び出し)
# ============================================================
def analyze_task(text: str) -> dict:
    prompt = f"""
あなたはタスク管理アシスタントです。与えられたタスク文から以下を推定し、
**JSONのみ**を返してください。文章やコードフェンスは不要です。

- 期限: 可能なら YYYY-MM-DD（ゼロ埋め）。わからなければ "不明"
- 優先度: "高" | "中" | "低"

タスク: {text}
出力例: {{"期限":"2025-08-10","優先度":"高"}}
"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()

    try:
        data = json.loads(raw)
    except Exception:
        data = {}

    due_raw = (data.get("期限") or data.get("due_date") or "").strip()
    pr_raw  = (data.get("優先度") or data.get("priority") or "中").strip()

    # 期限正規化
    due_iso = None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_raw):
        due_iso = due_raw
    if not due_iso:
        due_iso = _iso_from_loose_str(due_raw)
    if not due_iso:
        due_iso = _parse_relative_ja(due_raw)
    if not due_iso or due_raw in ("", "不明", "unknown", "UNKNOWN", "N/A"):
        due_iso = "不明"

    # 優先度正規化
    if pr_raw.lower() in ("high", "urgent", "重要", "至急"):
        pr = "高"
    elif pr_raw.lower() in ("low", "低"):
        pr = "低"
    else:
        pr = "中"

    return {"due_date": due_iso, "priority": pr}

# ============================================================
# ルート
# ============================================================
@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    q = data.get("question", "")
    parsed = analyze_task(q)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO tasks (content, due_date, priority) VALUES (?,?,?)",
                  (q, parsed["due_date"], parsed["priority"]))
        conn.commit()
    return jsonify({"answer": f"タスクを登録しました: {parsed}"})


@app.route("/tasks", methods=["GET"])
def get_tasks():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, content, due_date, priority FROM tasks")
        rows = [{"id": r[0], "content": r[1], "due_date": r[2], "priority": r[3]} for r in c.fetchall()]
    return jsonify(rows)


# ============================================================
# 一括修正用ルート (作業後は削除推奨)
# ============================================================
@app.route("/admin/fix_due_dates", methods=["POST"])
def fix_due_dates():
    fixed = 0
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, due_date FROM tasks")
        rows = c.fetchall()
        for tid, due in rows:
            if not due:
                new_due = "不明"
            elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(due)):
                new_due = due
            else:
                new_due = (_iso_from_loose_str(str(due))
                           or _parse_relative_ja(str(due))
                           or "不明")
            if new_due != due:
                c.execute("UPDATE tasks SET due_date=? WHERE id=?", (new_due, tid))
                fixed += 1
        conn.commit()
    return jsonify({"fixed": fixed})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

# --- 追加ここから ---
import re
from datetime import datetime, timedelta
import sqlite3
from flask import jsonify

# version 確認用（デプロイ確認のため・任意）
APP_VERSION = "fixer-1"

@app.route("/version")
def version():
    return APP_VERSION


def _iso_from_loose_str(s: str) -> str | None:
    """
    YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD のようなゆるい日付表記を
    ISO (YYYY-MM-DD) に正規化
    """
    if not isinstance(s, str):
        return None
    s = s.strip()
    m = re.fullmatch(r"(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


def _parse_relative_ja(s: str) -> str | None:
    """
    日本語の相対日付をISOに変換
    例: 今日, 明日, 明後日, 来週, 3日後, 2週間後, 来月, 1か月後
    """
    if not isinstance(s, str):
        return None
    t = datetime.now().date()
    s = s.strip()

    if s in ("今日", "本日"):
        return t.isoformat()
    if s in ("明日", "あした"):
        return (t + timedelta(days=1)).isoformat()
    if s in ("明後日", "あさって"):
        return (t + timedelta(days=2)).isoformat()
    if s.startswith("来週"):
        return (t + timedelta(days=7)).isoformat()

    m = re.fullmatch(r"(\d+)\s*日後", s)
    if m:
        return (t + timedelta(days=int(m.group(1)))).isoformat()

    m = re.fullmatch(r"(\d+)\s*週間?後", s)
    if m:
        return (t + timedelta(days=7*int(m.group(1)))).isoformat()

    m = re.fullmatch(r"(\d+)\s*(か月|ヶ月|月)後", s)
    if m:
        return (t + timedelta(days=30*int(m.group(1)))).isoformat()

    if s == "来月":
        return (t + timedelta(days=30)).isoformat()

    return None


@app.route("/admin/fix_due_dates", methods=["POST"])
def fix_due_dates():
    """
    DB内の既存の due_date を正規化する。
    例: "unknown", "不明", "2025/8/7" → "2025-08-07" or "不明"
    ※ 作業後はこのルートを削除/コメントアウトするのを推奨。
    """
    DB_PATH = "tasks.db"  # あなたのアプリが使っているDBパス
    fixed = 0
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, due_date FROM tasks")
        for tid, due in c.fetchall():
            original = str(due) if due is not None else ""
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", original):
                new_due = original
            else:
                new_due = (_iso_from_loose_str(original)
                           or _parse_relative_ja(original)
                           or "不明")
            if new_due != original:
                c.execute("UPDATE tasks SET due_date=? WHERE id=?", (new_due, tid))
                fixed += 1
        conn.commit()
    return jsonify({"fixed": fixed})
# --- 追加ここまで ---
