import os
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import functions
from datetime import datetime
import sqlite3

app = Flask(__name__)

# Init client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Create new assistant or load existing
assistant_id = functions.create_assistant(client)

# Dictionary to store thread IDs for each role
role_threads = {}

def init_db():
    conn = sqlite3.connect('transcripts.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  thread_id TEXT,
                  role TEXT,
                  speaker TEXT,
                  timestamp TEXT,
                  message TEXT)''')
    conn.commit()
    conn.close()

def insert_message_to_db(thread_id, role, speaker, message):
    conn = sqlite3.connect('transcripts.db')
    c = conn.cursor()
    timestamp = datetime.utcnow().isoformat() + "Z"
    c.execute("INSERT INTO messages (thread_id, role, speaker, timestamp, message) VALUES (?, ?, ?, ?, ?)",
              (thread_id, role, speaker, timestamp, message))
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['GET'])
def start_conversation():
    role = request.args.get('role')
    if role in role_threads:
        return jsonify({"thread_id": role_threads[role]})
    thread = client.beta.threads.create()
    role_threads[role] = thread.id
    return jsonify({"thread_id": thread.id})

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_role = data.get('role', '')
    thread_id = role_threads.get(user_role)
    if not thread_id:
        return jsonify({"error": "No active conversation for this role"}), 400
    user_input = data.get('message', '')

    insert_message_to_db(thread_id, user_role, "user", user_input)

    # Add the user's role and message to the thread
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=f"[Role: {user_role}] {user_input}"
    )

    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    while True:
        run_status = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        if run_status.status == 'completed':
            break

    messages = client.beta.threads.messages.list(thread_id=thread_id)
    assistant_response = messages.data[0].content[0].text.value

    insert_message_to_db(thread_id, user_role, "assistant", assistant_response)

    return jsonify({"response": assistant_response})

@app.route('/transcripts/<role>/<thread_id>', methods=['GET'])
def get_transcript(role, thread_id):
    conn = sqlite3.connect('transcripts.db')
    c = conn.cursor()
    c.execute("SELECT * FROM messages WHERE thread_id=? AND role=? ORDER BY timestamp", (thread_id, role))
    messages = c.fetchall()
    conn.close()
    return jsonify([{"id": m[0], "thread_id": m[1], "role": m[2], "speaker": m[3], "timestamp": m[4], "message": m[5]} for m in messages])

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
