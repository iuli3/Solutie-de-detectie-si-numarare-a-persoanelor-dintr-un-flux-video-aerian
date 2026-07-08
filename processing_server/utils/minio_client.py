from minio import Minio
from minio.error import S3Error
import os

# Configurare Client
# secure=False pentru ca suntem pe localhost (HTTP, nu HTTPS)
minio_client = Minio(
    os.getenv("MINIO_ENDPOINT", "127.0.0.1:19000"),  # trece prin tunel spre laptopul tau
    access_key=os.getenv("MINIO_ACCESS_KEY", "admin"),
    secret_key=os.getenv("MINIO_SECRET_KEY", "parola_sigura"),
    secure=os.getenv("MINIO_SECURE", "0") == "1"
)

BUCKET_NAME = os.getenv("MINIO_BUCKET", "licenta-videos")

def init_minio():
    """Verifica daca bucket-ul exista, daca nu, il creeaza."""
    try:
        if not minio_client.bucket_exists(BUCKET_NAME):
            minio_client.make_bucket(BUCKET_NAME)
            print(f"[MinIO] Bucket '{BUCKET_NAME}' creat cu succes.")
        else:
            print(f"[MinIO] Bucket '{BUCKET_NAME}' exista deja.")
    except S3Error as e:
        print(f"[MinIO] Eroare la initializare: {e}")

def download_file_from_minio(object_name, local_path, progress_callback=None):

    try:
        stat = minio_client.stat_object(BUCKET_NAME, object_name)
        total_size = stat.size
        print(f"[MinIO] Incepe descarcare: {object_name} ({total_size / (1024*1024):.1f} MB)")
        
        response = minio_client.get_object(BUCKET_NAME, object_name)
        bytes_downloaded = 0
        chunk_size = 8 * 1024 * 1024  
        
        with open(local_path, 'wb') as file_data:
            for chunk in response.stream(chunk_size):
                file_data.write(chunk)
                bytes_downloaded += len(chunk)
                
                if progress_callback:
                    progress_callback(bytes_downloaded, total_size)
        
        response.close()
        response.release_conn()
        print(f"[MinIO]  Descarcare completa: {local_path}")
        return True
        
    except S3Error as e:
        print(f"[MinIO] Eroare la descarcare: {e}")
        return False
    except Exception as e:
        print(f"[MinIO] Eroare neasteptata: {e}")
        return False

def upload_file_to_minio(local_path, object_name):

    try:
        minio_client.fput_object(
            BUCKET_NAME, 
            object_name, 
            local_path,
        )
        print(f"[MinIO] Upload reusit: {object_name}")
        return True
    except S3Error as e:
        print(f"[MinIO] Eroare la upload: {e}")
        return False