from flask import Flask, request, jsonify
from openai import OpenAI
import os

app = Flask(__name__)

# OpenAI クライアント初期化（Render の Environment Variables で OPENAI_API_KEY を設定）
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

@app.route("/")
def home():
    return "Service is running!"

@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json() or {}
    question = data.get("question", "")
    if not question:
        return jsonify({"error": "No question provided"}), 400

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": question}
        ],
        temperature=0.2,
    )
    return jsonify({"answer": resp.choices[0].message.content})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
