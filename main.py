from dotenv import load_dotenv



# Set env variables from .env file
# Print a warning if .env file is missing or cannot be loaded
try:
    load_dotenv()
    print("Environment variables loaded from .env file.")
except Exception as e:
    print(f"Warning: Could not load .env file. {e}")


