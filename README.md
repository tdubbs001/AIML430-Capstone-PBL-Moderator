# Bemori - Water For Life Simulation

## Project Overview
Bemori - Water For Life Simulation is an interactive, project-based learning simulation. It simulates an educational environment where participants engage by playing assigned roles, receiving guidance from an AI moderator. The simulation fosters collaborative learning, with AI-driven support powered by OpenAI's language model.

## Features
- **AI Assistance**: Utilizes GPT-4 to guide simulation participants.
- **Role Playing**: Assigns each participant a unique role with specific objectives.
- **Real-time Chat**: Supports interaction between users and the AI assistant via a web interface.
- **Data Persistence**: Uses PostgreSQL to store conversations and transcripts.

## Tech Stack
- Python 3.11
- Flask 3.0.3
- OpenAI API 1.51.2
- SQLAlchemy 2.0.35
- AP Scheduler 3.10.4
- PostgreSQL

## Setup and Installation

1. **Clone the Repository**
   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Environment Configuration**
   Ensure the following environment variables are set:
   - `OPENAI_API_KEY`: Your OpenAI API Key.
   - `DATABASE_URL`: PostgreSQL database URL.

3. **Install Dependencies**
   Install the necessary packages using:
   ```bash
   pip install -r requirements.txt
   ```
   Alternatively, dependencies can be managed using the `.replit` configuration or `pyproject.toml` file:
   ```bash
   replit nix-install
   ```

4. **Database Configuration**
   Set up your PostgreSQL database and ensure it is running, or use the predefined `DATABASE_URL`.

5. **Run the Application**
   Start the Flask server with:
   ```bash
   python main.py
   ```
   If using the Replit environment, simply press the Run button.

## Usage
- Access the simulation via the web interface at `http://localhost:5000`.
- Use the chat interface to communicate with the AI moderator.
- Transcripts of interactions will be saved in the database.

