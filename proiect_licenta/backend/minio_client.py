from minio import Minio
from minio.error import S3Error
import os
from dotenv import load_dotenv
load_dotenv()

minio_client = Minio(
    os.getenv('MINIO_ENDPOINT', '127.0.0.1:9000'),
    access_key=os.getenv('MINIO_ACCESS_KEY', 'admin'),
    secret_key=os.getenv('MINIO_SECRET_KEY', 'parola_sigura'),
    secure=os.getenv('MINIO_SECURE', 'False').lower() == 'true'
)

BUCKET_NAME = os.getenv('MINIO_BUCKET', 'licenta-videos')

def init_minio():
    """Verifică dacă bucket-ul există, dacă nu, îl creează."""
    try:
        if not minio_client.bucket_exists(BUCKET_NAME):
            minio_client.make_bucket(BUCKET_NAME)
            print(f"[MinIO] Bucket '{BUCKET_NAME}' creat cu succes.")
        else:
            print(f"[MinIO] Bucket '{BUCKET_NAME}' există deja.")
    except S3Error as e:
        print(f"[MinIO] Eroare la inițializare: {e}")

def upload_file_to_minio(local_path, object_name, metadata=None):
    """
    Încarcă un fișier local în MinIO.
    :param local_path: Calea fișierului pe disk (ex: uploads/video.mp4)
    :param object_name: Cum se va numi în MinIO (ex: user_1/video.mp4)
    """
    try:
        minio_client.fput_object(
            BUCKET_NAME, 
            object_name, 
            local_path,
            metadata=metadata,
        )
        print(f"[MinIO] Upload reușit: {object_name}")
        return True
    except S3Error as e:
        print(f"[MinIO] Eroare la upload: {e}")
        return False