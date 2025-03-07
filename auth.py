from flask import Blueprint, request, jsonify
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from pymongo import MongoClient
from datetime import datetime, UTC, timedelta
import os

# Initialize the Flask Blueprint
auth_bp = Blueprint('auth', __name__)


# Initialize MongoDB
client = MongoClient("mongodb://127.0.0.1:27017/")  # Ensure it's localhost, not "mongo"
db = client["face_auth_db"]
users_collection = db["users"]


# Initialize Encryption and JWT
bcrypt = Bcrypt()
jwt = JWTManager()

# ------  Register new user ------

@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new user by storing a hashed password in MongoDB.
    """
    data = request.json
    username = data.get("username")
    password = data.get("password")

    # Check if the user already exists
    if users_collection.find_one({"username": username}):
        return jsonify({"error": "User already exists"}), 400

    # Hash the password before storing it
    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    users_collection.insert_one({"username": username, "password": hashed_password})

    return jsonify({"message": "User registered successfully"}), 201

# ------  Login user ------

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Authenticate user and return a JWT token if credentials are valid.
    """
    data = request.json
    username = data.get("username") 
    password = data.get("password")

    # Fetch user details from MongoDB
    user = users_collection.find_one({"username": username})

    # Validate user credentials
    if not user or not bcrypt.check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid username or password"}), 401
    
    # Check if user already has a valid token
    existing_token = user.get("token")
    token_expiry = user.get("token_expiry")

    if existing_token and token_expiry:
        expiry_date = datetime.strptime(token_expiry, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        if expiry_date > datetime.now(UTC):
            return jsonify({"token": existing_token}), 200

    # Generate a new JWT token
    access_token = create_access_token(identity=username, expires_delta=timedelta(days=1))

    # Store the new token and its expiry in the database
    users_collection.update_one(
        {"username": username},
        {"$set": {
            "token": access_token,
            "token_expiry": (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        }}
    )
    return jsonify({"token": access_token}), 200

# ------  Logout user ------

@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    Log out the user by removing the stored token from the database.
    """
    username = get_jwt_identity()  # Get the username from the JWT token

    # Remove token details from the user's record
    users_collection.update_one(
        {"username": username},
        {"$unset": {"token": "", "token_expiry": ""}}
    )

    return jsonify({"message": "User logged out successfully"}), 200

@auth_bp.route('/protected', methods=['GET'])
@jwt_required()
def protected():
    """
    Access a protected route, only available to authenticated users.
    """
    return jsonify({"message": "Protected route accessed successfully"}), 200
