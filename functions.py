import json
import os
from openai import OpenAI

# def create_assistant(client):
#     assistant_file_path = 'assistant.json'

#     if os.path.exists(assistant_file_path):
#         with open(assistant_file_path, 'r') as file:
#             assistant_data = json.load(file)
#             assistant_id = assistant_data['assistant_id']
#             print("Loaded existing assistant ID.")
#     else:
#         assistant = client.beta.assistants.create(
#             name = 'AI Moderator - Bemori Water For Life Simulation',
#             instructions="""
#             You are an AI assistant for a chat application. Your role is to engage in conversation,
#             answer questions, and provide helpful information to users.
#             """,
#             model="gpt-4o",
#             tools=[{"type": "file_search"}],
#         )

#         with open(assistant_file_path, 'w') as file:
#             json.dump({'assistant_id': assistant.id}, file)
#             print("Created a new assistant and saved the ID.")

#         assistant_id = assistant.id

#     return assistant_id



def create_assistant_with_vector_store(
    client,
    assistant_name,
    assistant_instructions,
    model_name,
    vector_store_name,
    directory_path
):
    """
    Creates an assistant with a vector store, uploads files to it, and associates the vector store with the assistant.
    Prints and returns IDs of the assistant, vector store, and uploaded files.

    Parameters:
    - client: The OpenAI API client instance.
    - assistant_name: Name of the assistant.
    - assistant_instructions: Instructions for the assistant.
    - model_name: The model to use (e.g., "gpt-4").
    - vector_store_name: Name of the vector store.
    - directory_path: Path to the directory containing files to upload.

    Returns:
    - assistant: The created assistant object.
    - vector_store: The created vector store object.
    - file_ids: A dictionary of filename: file IDs uploaded to the vector store.
    """
    assistant_file_path = 'assistant.json'

    if os.path.exists(assistant_file_path):
        with open(assistant_file_path, 'r') as file:
            assistant_data = json.load(file)
            assistant_id = assistant_data['assistant_id']
            print("Loaded existing assistant ID.")
    else:
    
        try:
            # Create the assistant
            assistant = client.beta.assistants.create(
                name=assistant_name,
                instructions=assistant_instructions,
                model=model_name,
                tools=[{"type": "file_search"}],
            )
            print(f"Assistant created with ID: {assistant.id}")
    
            # Create a vector store
            vector_store = client.beta.vector_stores.create(name=vector_store_name)
            print(f"Vector store created with ID: {vector_store.id}")
    
            # Read files from directory
            file_paths = [os.path.join(directory_path, file) for file in os.listdir(directory_path)]
            file_streams = [open(path, "rb") for path in file_paths]
    
            # Upload files to vector store and poll for completion
            file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vector_store.id, files=file_streams
            )
    
            # Close the file streams
            for f in file_streams:
                f.close()
    
            # Print the status and file counts of the batch
            print(f"File batch status: {file_batch.status}")
            print(f"File counts: {file_batch.file_counts}")
    
            # List files in the vector store and collect their IDs
            files = client.beta.vector_stores.files.list(vector_store_id=vector_store.id)
            assistant_file_ids = {}
            print("Files in the vector store:")
            for file in files:
                filename = client.files.retrieve(file.id).filename
                print(f"- File ID: {file.id}, File Name: {filename}")
                assistant_file_ids[filename] = file.id
    
            # Update assistant to associate it with the vector store
            assistant = client.beta.assistants.update(
                assistant_id=assistant.id,
                tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
            )
            print(f"Assistant {assistant.id} updated with vector store {vector_store.id}")

            with open(assistant_file_path, 'w') as file:
                json.dump({'assistant_id': assistant.id}, file)
            
            assistant_id = assistant.id
            return assistant_id, vector_store, assistant_file_ids
    
        except Exception as e:
            print(f"An error occurred: {e}")
            return None, None, None