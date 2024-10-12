import os
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import functions
from datetime import datetime
import json
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# Database connection
def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv('PGHOST'),
        database=os.getenv('PGDATABASE'),
        user=os.getenv('PGUSER'),
        password=os.getenv('PGPASSWORD'),
        port=os.getenv('PGPORT')
    )
    return conn

# Initialize database
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Drop existing tables if they exist
    cur.execute("DROP TABLE IF EXISTS messages")
    cur.execute("DROP TABLE IF EXISTS conversations")
    
    cur.execute('''
        CREATE TABLE conversations (
            id SERIAL PRIMARY KEY,
            role VARCHAR(255) NOT NULL,
            thread_id VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE messages (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER REFERENCES conversations(id),
            sender VARCHAR(50) NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

# Init client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Create new assistant or load existing
assistant_id = functions.create_assistant(client)

# Dictionary to store thread IDs for each role
role_threads = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['GET'])
def start_conversation():
    role = request.args.get('role')
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT thread_id FROM conversations WHERE role = %s ORDER BY created_at DESC LIMIT 1", (role,))
    existing_thread = cur.fetchone()
    
    if existing_thread:
        thread_id = existing_thread['thread_id']
    else:
        thread = client.beta.threads.create()
        thread_id = thread.id
        cur.execute("INSERT INTO conversations (role, thread_id) VALUES (%s, %s)", (role, thread_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    role_threads[role] = thread_id
    return jsonify({"thread_id": thread_id})

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_role = data.get('role', '')
    thread_id = role_threads.get(user_role)
    if not thread_id:
        return jsonify({"error": "No active conversation for this role"}), 400
    user_input = data.get('message', '')

    conn = get_db_connection()
    cur = conn.cursor()

    # Save user message to database
    cur.execute("SELECT id FROM conversations WHERE thread_id = %s", (thread_id,))
    conversation_id = cur.fetchone()[0]
    cur.execute("INSERT INTO messages (conversation_id, sender, content) VALUES (%s, %s, %s)",
                (conversation_id, 'user', user_input))

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

    # Save assistant response to database
    cur.execute("INSERT INTO messages (conversation_id, sender, content) VALUES (%s, %s, %s)",
                (conversation_id, 'assistant', assistant_response))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"response": assistant_response})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
