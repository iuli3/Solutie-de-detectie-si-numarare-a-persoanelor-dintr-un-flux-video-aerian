import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from utils.migrate_db import migrate_db

if __name__ == "__main__":
    migrate_db()
