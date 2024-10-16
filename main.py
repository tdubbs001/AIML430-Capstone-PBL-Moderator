import os
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import functions
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

app = Flask(__name__)

# Init client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Create new assistant or load existing
assistant_id = functions.create_assistant(client)

# Set up database connection
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost/dbname')
engine = create_engine(DATABASE_URL)
Base = declarative_base()
Session = sessionmaker(bind=engine)

# Define Message model
class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True)
    thread_id = Column(String, nullable=False)
    role_type = Column(String, nullable=False)
    sender = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Define SimulationUpdate model
class SimulationUpdate(Base):
    __tablename__ = 'simulation_updates'

    id = Column(Integer, primary_key=True)
    thread_id = Column(String, nullable=False)
    role_type = Column(String, nullable=False)
    water_level = Column(Float, nullable=False)
    population = Column(Integer, nullable=False)
    resources = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Define Transcript model
class Transcript(Base):
    __tablename__ = 'transcripts'

    id = Column(Integer, primary_key=True)
    thread_id = Column(String, nullable=False)
    role_type = Column(String, nullable=False)
    transcript = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Create tables
Base.metadata.create_all(engine)

# Dictionary to store thread IDs for each role
role_threads = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['GET'])
def start_conversation():
    role = request.args.get('role')
    session = Session()
    
    if role in role_threads:
        thread_id = role_threads[role]
    else:
        thread = client.beta.threads.create()
        thread_id = thread.id
        role_threads[role] = thread_id
    
    # Check if thread exists in database
    existing_message = session.query(Message).filter_by(thread_id=thread_id).first()
    if not existing_message:
        # Create a new thread entry in the database
        new_message = Message(thread_id=thread_id, role_type=role, sender='system', message='Conversation started')
        session.add(new_message)
        session.commit()
    
    session.close()
    return jsonify({"thread_id": thread_id})

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_role = data.get('role', '')
    thread_id = role_threads.get(user_role)
    if not thread_id:
        return jsonify({"error": "No active conversation for this role"}), 400
    user_input = data.get('message', '')

    session = Session()

    # Save user message to database
    user_message = Message(thread_id=thread_id, role_type=user_role, sender='user', message=user_input)
    session.add(user_message)
    session.commit()

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

    # Save assistant message to database
    assistant_message = Message(thread_id=thread_id, role_type=user_role, sender='assistant', message=assistant_response)
    session.add(assistant_message)
    session.commit()

    # Update or create transcript
    transcript = session.query(Transcript).filter_by(thread_id=thread_id, role_type=user_role).first()
    if transcript:
        transcript.transcript += f"\nUser: {user_input}\nAssistant: {assistant_response}"
        transcript.updated_at = datetime.utcnow()
    else:
        new_transcript = Transcript(
            thread_id=thread_id,
            role_type=user_role,
            transcript=f"User: {user_input}\nAssistant: {assistant_response}"
        )
        session.add(new_transcript)
    session.commit()

    session.close()

    return jsonify({"response": assistant_response})

@app.route('/end_session', methods=['POST'])

def analyze_transcript_with_openai(transcript):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an AI assistant analyzing a conversation transcript about water management in Bemori. Provide a concise update on the key points discussed."},
                {"role": "user", "content": f"Analyze this transcript and provide a brief update on the key points:\n\n{transcript}"}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error in analyzing transcript: {str(e)}")
        return None

def save_simulation_updates(session, role, update):
    if not update:
        return

    new_update = SimulationUpdate(
        role_type=role,
        update_content=update  # Changed from 'update' to 'update_content'
    )
    session.add(new_update)
    session.commit()

def end_session():
    data = request.json
    thread_id = data.get('thread_id')
    role = data.get('role')
    
    session = Session()
    
    # Fetch all messages for the thread
    messages = session.query(Message).filter_by(thread_id=thread_id, role_type=role).order_by(Message.timestamp).all()
    
    # Compile messages into a transcript
    transcript_text = "\n".join([f"{msg.sender.capitalize()}: {msg.message}" for msg in messages])
    
    # Update or create transcript
    transcript = session.query(Transcript).filter_by(thread_id=thread_id, role_type=role).first()
    if transcript:
        transcript.transcript = transcript_text
        transcript.updated_at = datetime.utcnow()
    else:
        new_transcript = Transcript(
            thread_id=thread_id,
            role_type=role,
            transcript=transcript_text
        )
        session.add(new_transcript)

    update = analyze_transcript_with_openai(transcript_text)
    if update:
        save_simulation_updates(session, role, update)
    
    # Mark the session as ended in the database
    end_message = Message(thread_id=thread_id, role_type=role, sender='system', message='Session ended')
    session.add(end_message)
    
    session.commit()
    session.close()

    
    
    return jsonify({"status": "success", "message": "Session ended, transcript saved and simulation updated"})
    

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

