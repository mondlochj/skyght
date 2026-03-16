import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost:5432/skyght')
JWT_SECRET = os.getenv('JWT_SECRET', 'supersecretkey')
PORT = int(os.getenv('PORT', 3000))
