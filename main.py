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

# Define Transcript model
class Transcript(Base):
    __tablename__ = 'transcripts'

    id = Column(Integer, primary_key=True)
    thread_id = Column(String, nullable=False)
    role_type = Column(String, nullable=False)
    transcript = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Define TranscriptAnalysis model
class TranscriptAnalysis(Base):
    __tablename__ = 'transcript_analysis'

    id = Column(Integer, primary_key=True)
    thread_id = Column(String, nullable=False)
    role_type = Column(String, nullable=False)
    analysis = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

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
        transcript.updated_at = datetime.now()
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
        transcript.updated_at = datetime.now()
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

def analyze_transcript(thread_id, role_type):
    logger.info(f"Starting analysis for thread_id: {thread_id}, role_type: {role_type}")
    session = Session()
    transcript = session.query(Transcript).filter_by(thread_id=thread_id, role_type=role_type).first()
    
    if transcript:
        logger.info(f"Found transcript for thread_id: {thread_id}, role_type: {role_type}")
        # Use OpenAI API to analyze the transcript
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an AI assistant tasked with analyzing conversation transcripts in a Project Based Learning simulation. Your task is to analyze the messages from the user only. The user has a role type associated with them, along with timestamps for messages. This is reported in the transcript. I want you to then produce a report outlining what has happened in the transcript. The purpose of this report is to update the moderator on the state of the simulation for this role."},
                {"role": "user", "content": f"Here is the transcript from {role_type}:\n\n{transcript.transcript}"}
            ]
        )
        
        analysis = response.choices[0].message.content
        logger.info(f"Analysis completed for thread_id: {thread_id}, role_type: {role_type}")
        
        # Save or update the analysis in the database
        existing_analysis = session.query(TranscriptAnalysis).filter_by(thread_id=thread_id, role_type=role_type).first()
        if existing_analysis:
            existing_analysis.analysis = analysis
            existing_analysis.created_at = datetime.utcnow()
            logger.info(f"Updated existing analysis for thread_id: {thread_id}, role_type: {role_type}")
        else:
            new_analysis = TranscriptAnalysis(thread_id=thread_id, role_type=role_type, analysis=analysis)
            session.add(new_analysis)
            logger.info(f"Created new analysis for thread_id: {thread_id}, role_type: {role_type}")
        
        session.commit()
    else:
        logger.warning(f"No transcript found for thread_id: {thread_id}, role_type: {role_type}")
    
    session.close()

def export_transcripts_to_md(transcripts):
    session = Session()
    for transcript in transcripts:
        # Determine the file name
        md_filename = f"transcripts/{transcript.role_type}_{transcript.thread_id}.md"

        # Ensure the directory exists
        os.makedirs(os.path.dirname(md_filename), exist_ok=True)

        # Write to the markdown file
        with open(md_filename, 'w') as f:
            f.write(f"# Transcript for {transcript.role_type}\n")
            f.write(f"_Thread ID: {transcript.thread_id}_\n")
            f.write("---\n\n")
            f.write(transcript.transcript)

        logger.info(f"Saved transcript for role type '{transcript.role_type}' to {md_filename}")
    session.close()

def periodic_analysis():
    logger.info("Starting periodic analysis")
    session = Session()
    time_interval = datetime.now() - timedelta(minutes=1)
    
    transcripts = session.query(Transcript).filter(
        (Transcript.created_at > time_interval) | 
        (Transcript.updated_at > time_interval)
    ).all()

    logger.info(f"Found {len(transcripts)} new transcripts to analyze")
    if not transcripts:
        logger.info("No transcripts found for analysis")
    else:
        for transcript in transcripts:
            export_transcripts_to_md(transcripts)
    session.close()
    logger.info("Periodic analysis completed")

# Set up the scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=periodic_analysis, trigger="interval", minutes=1)  # Changed from hours=1 to minutes=1
scheduler.start()

logger.info("Scheduler started with 1-minute interval")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
