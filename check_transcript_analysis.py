import os
import sys
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable is not set.")
    sys.exit(1)

try:
    engine = create_engine(DATABASE_URL)
except Exception as e:
    print(f"Error creating database engine: {str(e)}")
    sys.exit(1)

def check_transcript_analysis():
    try:
        with engine.connect() as connection:
            # Check if there are any entries in the transcript_analysis table
            result = connection.execute(text("SELECT COUNT(*) FROM transcript_analysis"))
            count = result.scalar()
            
            print(f"Total entries in transcript_analysis table: {count}")

            # Check for entries in the last hour
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            result = connection.execute(text("SELECT COUNT(*) FROM transcript_analysis WHERE created_at > :one_hour_ago"),
                                        {"one_hour_ago": one_hour_ago})
            recent_count = result.scalar()
            
            print(f"Entries in the last hour: {recent_count}")
    except Exception as e:
        print(f"Error querying database: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    check_transcript_analysis()
