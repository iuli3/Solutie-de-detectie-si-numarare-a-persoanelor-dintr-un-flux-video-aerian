# backend/auth.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from extensions import db  # Importăm db
from models import User    # Importăm clasa User din models.py
from datetime import timedelta

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()

    # 1. Validare date intrare
    # Câmpurile obligatorii din noul formular
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Email-ul și parola sunt obligatorii'}), 400

    email = data.get('email')
    password = data.get('password')
    first_name = data.get('firstName') # Atenție la case (camelCase din frontend)
    last_name = data.get('lastName')

    # 2. Verificăm dacă email-ul există deja
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Acest email este deja înregistrat'}), 409

    try:
        # 3. Creăm userul
        # NOTĂ: Setăm username = email pentru simplitate
        new_user = User(
            username=email, 
            email=email,
            first_name=first_name,
            last_name=last_name
        )
        
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        # 4. Login automat după register
        access_token = create_access_token(identity=str(new_user.id), expires_delta=timedelta(days=1))

        return jsonify({
            'message': 'Cont creat cu succes',
            'user': new_user.to_dict(),
            'access_token': access_token
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"[AUTH ERROR] {e}")
        return jsonify({'error': 'Eroare la crearea contului'}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()

    # 1. Validare input
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Lipsesc datele de autentificare'}), 400

    username = data.get('username')
    password = data.get('password')

    # 2. Căutăm utilizatorul în baza de date
    user = User.query.filter_by(username=username).first()

    # 3. Verificăm parola (folosind funcția check_password din models.py)
    if user and user.check_password(password):
        # Generăm token valabil 24 ore
        access_token = create_access_token(identity=str(user.id), expires_delta=timedelta(days=1))
        
        return jsonify({
            'message': 'Autentificare reușită',
            'access_token': access_token,
            # Returnăm tot obiectul user (fără parolă) folosind to_dict()
            'user': user.to_dict() 
        }), 200
    else:
        return jsonify({'error': 'Nume de utilizator sau parolă incorectă'}), 401


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """
    Rută pentru a obține datele utilizatorului curent pe baza token-ului.
    Utila pentru a reîmprospăta datele în frontend la refresh.
    """
    user_id = get_jwt_identity()
    user = db.session.get(User, int(user_id))

    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({'user': user.to_dict()}), 200