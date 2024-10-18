import os
import json
from flask import Flask, request, jsonify, render_template
import functions
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
from sqlalchemy.orm import declarative_base, sessionmaker
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from openai import OpenAI

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
model_name = 'gpt-4o'
vector_store_name = 'Simulation Documents'
directory_path = './simulation_docs'

# Global variables for assistant_id and vector_store
global assistant_id, vector_store
assistant_id = None
vector_store = None

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
    if vector_store:
        logger.info(f"Vector store created or loaded with ID: {vector_store.id}")
    else:
        logger.error("Failed to create or load vector store")
except Exception as e:
    logger.error(f"An error occurred while creating or loading the assistant and vector store: {str(e)}")

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
    if not data:
        return jsonify({"error": "No JSON data received"}), 400
    user_role = data.get('role')
    thread_id = data.get('thread_id')
    user_input = data.get('message')

    if not user_role or not thread_id or not user_input:
        return jsonify({"error": "Missing required fields"}), 400

    session = Session()

    try:
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

        # Check if assistant_id is available
        if assistant_id is None:
            raise ValueError("Assistant ID is not available")

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
            elif run_status.status == 'failed':
                raise ValueError(f"Run failed: {run_status.last_error}")

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        assistant_response = ""
        for content in messages.data[0].content:
            if content.type == 'text':
                assistant_response += content.text.value
            elif content.type == 'image_file':
                assistant_response += f"[Image: {content.image_file.file_id}]"
        if not assistant_response:
            raise ValueError("No valid response content found")

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

        return jsonify({"response": assistant_response})

    except Exception as e:
        logger.error(f"Error in chat route: {str(e)}")
        return jsonify({"error": str(e)}), 500

    finally:
        session.close()

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

def update_files_in_vector_store():
    global vector_store
    logger.info("Starting vector store update process")
    
    if vector_store is None:
        logger.error("Vector store is not initialized")
        return

    session = Session()
    time_interval = datetime.utcnow() - timedelta(minutes=1)

    # Retrieve transcripts modified within the last minute
    transcripts = session.query(Transcript).filter(
        (Transcript.created_at > time_interval) | 
        (Transcript.updated_at > time_interval)
    ).all()

    logger.info(f"Found {len(transcripts)} transcripts to update")

    if not transcripts:
        logger.info("No transcripts found for update")
    else:
        for transcript in transcripts:
            # Extract the filename
            transcript_name = f"{transcript.role_type}_{transcript.thread_id}.md"

            try:
                # Check if the file exists in the vector store and delete it
                vector_store_files = client.beta.vector_stores.files.list(vector_store_id=vector_store.id)
                for file in vector_store_files:
                    filename = client.files.retrieve(file.id).filename
                    if filename == transcript_name:
                        client.beta.vector_stores.files.delete(file_id=file.id, vector_store_id=vector_store.id)
                        logger.info(f"Deleted file {filename} from vector store")
                        break

                # Prepare the transcript content for upload
                file_content = f"# Transcript for {transcript.role_type}\n_Thread ID: {transcript.thread_id}_\n---\n\n{transcript.transcript}"
                temp_file_path = f"/tmp/{transcript_name}"
                with open(temp_file_path, 'w') as file:
                    file.write(file_content)

                # Upload the updated file to the vector store
                with open(temp_file_path, 'rb') as file_stream:
                    uploaded_file = client.beta.vector_stores.file_batches.upload_and_poll(
                        vector_store_id=vector_store.id, files=[file_stream]
                    )
                logger.info(f"Uploaded file {transcript_name} to vector store")

                # Remove the temporary file
                os.remove(temp_file_path)

            except Exception as e:
                logger.error(f"Error processing transcript {transcript.thread_id}: {str(e)}")

    session.close()
    logger.info("Vector store update process completed")

# Set up the scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=update_files_in_vector_store, trigger="interval", minutes=1)
scheduler.start()

logger.info("Scheduler started with 1-minute interval")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
