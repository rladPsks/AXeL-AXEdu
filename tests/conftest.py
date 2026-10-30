import os

# Real local API credentials must never affect test behavior or cause paid calls.
os.environ['SCHOOL_AGENT_LOAD_DOTENV'] = '0'
