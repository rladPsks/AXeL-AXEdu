import os

# A developer's local .env must never change test behaviour.
os.environ['SCHOOL_AGENT_LOAD_DOTENV'] = '0'
