#!/usr/bin/env python3
"""
Script pentru a adauga coloane noi la tabelul Video in PostgreSQL.
Executa: python migrate_db.py
"""

import os
import sys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from sqlalchemy import text
from flask import Flask
from extensions import db
from models import Video, User, PersonLog

# Configurare Flask
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL', 'postgresql://admin:parola_sigura@127.0.0.1:5433/licenta_db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

def add_columns():
    """Adauga coloane noi la tabelul Video"""
    with app.app_context():
        try:
            engine = db.engine
            
            # SQL pentru adaugarea coloanelor
            sql_statements = [
                """
                ALTER TABLE video
                ADD COLUMN IF NOT EXISTS heatmap_video_path VARCHAR(500);
                """,
                """
                ALTER TABLE video
                ADD COLUMN IF NOT EXISTS max_people_in_frame INTEGER DEFAULT 0;
                """,
                """
                ALTER TABLE video
                ADD COLUMN IF NOT EXISTS avg_people_per_frame FLOAT DEFAULT 0.0;
                """,
                """
                ALTER TABLE video
                ADD COLUMN IF NOT EXISTS dm_model_used VARCHAR(50);
                """,
                # minio_path devine nullable pentru live feeds
                """
                ALTER TABLE video
                ALTER COLUMN minio_path DROP NOT NULL;
                """,
            ]
            
            with engine.connect() as connection:
                for sql in sql_statements:
                    try:
                        connection.execute(text(sql.strip()))
                        print(f" Executat: {sql.strip()[:60]}...")
                    except Exception as e:
                        print(f"  Eroare la: {sql.strip()[:60]}... → {e}")
                
                connection.commit()
                print("\n Migratie completa!")
        
        except Exception as e:
            print(f" Eroare critica: {e}")
            sys.exit(1)

if __name__ == '__main__':
    print(" Se adauga coloane noi la tabelul Video...")
    add_columns()
