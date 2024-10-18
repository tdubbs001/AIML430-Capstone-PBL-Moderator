import os
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import functions
from datetime import datetime
from datetime import timedelta
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from apscheduler.schedulers.background import BackgroundScheduler
import logging

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Init client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
logger.info(f"OpenAI client initialized with API key: {'*' * len(os.getenv('OPENAI_API_KEY', ''))}")

# Define parameters
assistant_name = 'AI Moderator - Bemori Water For Life Simulation'
assistant_instructions = 'You are a helpful assistant designed to moderate a project-based learning simulation.'
model_name = 'gpt-4'
vector_store_name = 'Simulation Documents'
directory_path = 'simulation_docs'

# Global variable for assistant_id
global assistant_id
assistant_id = None

# Call the function and handle potential errors
try:
    assistant_id, vector_store, file_ids = functions.create_assistant_with_vector_store(
        client,
        assistant_name,
        assistant_instructions,
        model_name,
        vector_store_name,
        directory_path
    )
    if assistant_id:
        logger.info(f"Assistant created or loaded with ID: {assistant_id}")
    else:
        logger.error("Failed to create or load assistant")
except Exception as e:
    logger.error(f"An error occurred while creating or loading the assistant: {str(e)}")

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
    global assistant_id
    data = request.json
    user_role = data.get('role', '')
    thread_id = role_threads.get(user_role)
    if not thread_id:
        logger.error(f"No active conversation for role: {user_role}")
        return jsonify({"error": "No active conversation for this role"}), 400
    user_input = data.get('message', '')

    session = Session()

    # Save user message to database
    user_message = Message(thread_id=thread_id, role_type=user_role, sender='user', message=user_input)
    session.add(user_message)
    session.commit()

    try:
        # Add the user's role and message to the thread
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=f"[Role: {user_role}] {user_input}"
        )
    except Exception as e:
        logger.error(f"Error creating message: {str(e)}")
        return jsonify({"error": "Failed to create message"}), 500

    # Check if assistant_id is available
    if assistant_id is None:
        logger.error("Assistant ID is not available")
        return jsonify({"error": "Assistant not initialized"}), 500

    try:
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id
        )
    except Exception as e:
        logger.error(f"Error creating run: {str(e)}")
        return jsonify({"error": "Failed to create run"}), 500

    try:
        while True:
            run_status = client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )
            if run_status.status == 'completed':
                break
            elif run_status.status == 'failed':
                logger.error(f"Run failed: {run_status.last_error}")
                return jsonify({"error": "Assistant run failed"}), 500
    except Exception as e:
        logger.error(f"Error retrieving run status: {str(e)}")
        return jsonify({"error": "Failed to retrieve run status"}), 500

    try:
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        assistant_response = messages.data[0].content[0].text.value
    except Exception as e:
        logger.error(f"Error retrieving messages: {str(e)}")
        return jsonify({"error": "Failed to retrieve messages"}), 500

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
def end_session():
    data = request.json
    thread_id = data.get('thread_id')
    role = data.get('role')
    
    session = Session()
    
    # Fetch all messages for the thread
    messages = session.query(Message).filter_by(thread_id=thread_id, role_type=role).order_by(Message.timestamp).all()
    
    # Compile messages into a transcript
    transcript_text = "\n\n".join([f"{msg.sender.capitalize()} ({msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')}): {msg.message}" for msg in messages])
    
    # Update or create transcript
    transcript = session.query(Transcript).filter_by(thread_id=thread_id, role_type=role).first()
    if transcript:
        transcript.transcript = f'{transcript_text}\n{transcript.transcript}'
        transcript.updated_at = datetime.utcnow()
    else:
        new_transcript = Transcript(
            thread_id=thread_id,
            role_type=role,
            transcript=transcript_text
        )
        session.add(new_transcript)
    
    # Mark the session as ended in the database
    end_message = Message(thread_id=thread_id, role_type=role, sender='system', message='Session ended')
    session.add(end_message)
    
    session.commit()
    session.close()
    
    return jsonify({"status": "success", "message": "Session ended and transcript saved"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
