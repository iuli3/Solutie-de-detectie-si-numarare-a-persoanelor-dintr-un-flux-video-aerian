"""
Script de migrație pentru a adăuga coloana processed_video_path în tabela Video
Rulați cu: python migrate_add_processed_video_path.py
"""
import psycopg2

def migrate():
    try:
        # Conectare la baza de date
        conn = psycopg2.connect(
            host="localhost",
            port=5433,
            database="licenta_db",
            user="admin",
            password="parola_sigura"
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Verifică dacă coloana există deja
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='video' AND column_name='processed_video_path'"
        )
        
        if cursor.fetchone():
            print("✅ Coloana 'processed_video_path' există deja!")
            cursor.close()
            conn.close()
            return
        
        # Adaugă coloana
        print("📝 Adăugăm coloana 'processed_video_path'...")
        cursor.execute(
            "ALTER TABLE video ADD COLUMN processed_video_path VARCHAR(500)"
        )
        print("✅ Migrație completă! Coloana 'processed_video_path' a fost adăugată.")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Eroare la migrație: {e}")

if __name__ == "__main__":
    migrate()
