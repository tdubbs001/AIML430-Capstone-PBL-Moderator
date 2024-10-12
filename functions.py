import json
import os
from openai import OpenAI

def create_assistant(client):
    assistant_file_path = 'assistant.json'

    if os.path.exists(assistant_file_path):
        with open(assistant_file_path, 'r') as file:
            assistant_data = json.load(file)
            assistant_id = assistant_data['assistant_id']
            print("Loaded existing assistant ID.")
    else:
        assistant = client.beta.assistants.create(
            instructions="""
            You are an AI assistant for a chat application. Your role is to engage in conversation,
            answer questions, and provide helpful information to users.
            """,
            model="gpt-4-turbo-preview",
        )

        with open(assistant_file_path, 'w') as file:
            json.dump({'assistant_id': assistant.id}, file)
            print("Created a new assistant and saved the ID.")

        assistant_id = assistant.id

    return assistant_id
