import os
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import functions
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from apscheduler.schedulers.background import BackgroundScheduler
import logging

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
role_threads = {
    'undp_head': None,
    'undp_water_project_manager': None,
    'local_government_official': None,
    'local_ngo_officer': None,
    'international_ngo_officer': None,
    'bilateral_aid_officer': None,
    'eu_officer': None,
    'village_chief': None,
    'womens_group_rep': None,
    'water_division_director': None
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['GET'])
def start_conversation():
    role = request.args.get('role')
    session = Session()
    
    if role_threads[role] is None:
        thread = client.beta.threads.create()
        role_threads[role] = thread.id
        
        # Create a new thread entry in the database
        new_message = Message(thread_id=thread.id, role_type=role, sender='system', message='Conversation started')
        session.add(new_message)
        session.commit()
    
    session.close()
    return jsonify({"thread_id": role_threads[role]})

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_role = data.get('role', '')
    thread_id = role_threads[user_role]
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
def end_session():
    data = request.json
    role = data.get('role')
    thread_id = role_threads[role]
    
    session = Session()
    
    # Fetch all messages for the thread
    messages = session.query(Message).filter_by(thread_id=thread_id, role_type=role).order_by(Message.timestamp).all()
    
    # Compile messages into a transcript
    transcript_text = "\n\n".join([f"{msg.sender.capitalize()} ({msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')}): {msg.message}" for msg in messages])
    
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
    
    # Mark the session as ended in the database
    end_message = Message(thread_id=thread_id, role_type=role, sender='system', message='Session ended')
    session.add(end_message)
    
    session.commit()
    session.close()
    
    return jsonify({"status": "success", "message": "Session ended and transcript saved"})

def analyze_transcript(thread_id, role_type):
    logger.info(f"Starting analysis for thread {thread_id} and role {role_type}")
    session = Session()
    transcript = session.query(Transcript).filter_by(thread_id=thread_id, role_type=role_type).first()
    
    if transcript:
        # Prepare the prompt for GPT-4
        prompt = f"""
        Analyze the following transcript of a conversation in the context of the Bemori - Water For Life Simulation.
        Focus on the following aspects:
        1. Key decisions made
        2. Challenges faced
        3. Strategies proposed
        4. Collaboration between different roles
        5. Impact on water resources and population

        Provide a concise summary of these aspects.

        Transcript:
        {transcript.transcript}
        """

        # Use GPT-4 to analyze the transcript
        try:
            response = client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": "You are an AI assistant tasked with analyzing transcripts from the Bemori - Water For Life Simulation."},
                    {"role": "user", "content": prompt}
                ]
            )

            analysis = response.choices[0].message.content

            # Save or update the analysis in the database
            existing_analysis = session.query(TranscriptAnalysis).filter_by(thread_id=thread_id, role_type=role_type).first()
            if existing_analysis:
                existing_analysis.analysis = analysis
                existing_analysis.created_at = datetime.utcnow()
            else:
                new_analysis = TranscriptAnalysis(thread_id=thread_id, role_type=role_type, analysis=analysis)
                session.add(new_analysis)

            session.commit()
            logger.info(f"Analysis completed and saved for thread {thread_id} and role {role_type}")
        except Exception as e:
            logger.error(f"Error during transcript analysis: {str(e)}")
    else:
        logger.warning(f"No transcript found for thread {thread_id} and role {role_type}")
    
    session.close()

def periodic_analysis():
    logger.info("Starting periodic analysis...")
    try:
        session = Session()
        # Get all active threads from the last 24 hours
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        recent_threads = session.query(Message.thread_id, Message.role_type).filter(Message.timestamp > cutoff_time).distinct().all()
        
        logger.info(f"Found {len(recent_threads)} recent threads to analyze")
        
        for thread_id, role_type in recent_threads:
            logger.info(f"Analyzing thread {thread_id} for role {role_type}")
            analyze_transcript(thread_id, role_type)
        
        session.close()
        logger.info("Periodic analysis completed successfully.")
    except Exception as e:
        logger.error(f"Error during periodic analysis: {str(e)}")

# Set up the scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=periodic_analysis, trigger="interval", minutes=1)  # Changed from hours=1 to minutes=1 for testing
scheduler.start()
logger.info("Scheduler started with periodic_analysis job")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
