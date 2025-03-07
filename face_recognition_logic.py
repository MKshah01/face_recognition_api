import os
import face_recognition
import numpy as np
import faiss
import cv2
from flask import Flask, request, jsonify
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from auth import auth_bp

app = Flask(__name__)
KNOWN_FACES_DIR = "E:/COMPANY/EMPLOYEE"
UPLOAD_FOLDER = "E:/COMPANY/EMPLOYEE"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Set Secret Key for JWT
app.config["JWT_SECRET_KEY"] = "your_secret_key"
jwt = JWTManager(app)

# Register Blueprint
app.register_blueprint(auth_bp, url_prefix="/auth")

# ------ Load known faces and create Faiss index ------

def load_known_faces():
    """Load known face encodings and names from the directory."""
    known_encodings = []
    known_names = []

    for filename in os.listdir(KNOWN_FACES_DIR):
        if filename.endswith((".jpg", ".png", ".jpeg")):
            img_path = os.path.join(KNOWN_FACES_DIR, filename)
            img = face_recognition.load_image_file(img_path)
            encoding = face_recognition.face_encodings(img)

            if encoding:
                known_encodings.append(encoding[0])
                known_names.append(os.path.splitext(filename)[0])

    return known_encodings, known_names

# ------ Face Recognition ------

def create_faiss_index(known_encodings):
    """Create and return a Faiss HNSW index for fast nearest neighbor search."""
    if known_encodings:
        known_encodings_np = np.array(known_encodings, dtype='float32')
        index = faiss.IndexHNSWFlat(len(known_encodings[0]), 32)
        index.add(known_encodings_np)
        return index
    return None

def recognize_faces_faiss(frame, index, known_names):
    """Recognize faces in a given frame using Faiss search."""
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb_frame)
    face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
    face_names = []

    for face_encoding in face_encodings:
        face_encoding_np = np.array([face_encoding], dtype='float32')
        distances, indices = index.search(face_encoding_np, 1)

        if indices[0][0] != -1 and distances[0][0] < 0.6:
            name = known_names[indices[0][0]]
        else:
            name = "Employee Not Found"
        
        face_names.append(name)
    
    return face_locations, face_names

# ------ Image Verification ------

def verify_images(image_files):
    """
    Compares three images and verifies if they contain the same face.
    :param image_files: List of three image file objects.
    :return: "Approved" if all images contain the same face, otherwise "Not Approved".
    """
    if len(image_files) != 3:
        return "Please upload exactly three images."
    
    encodings = []
    for file in image_files:
        np_arr = np.frombuffer(file.read(), np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        encoding = face_recognition.face_encodings(rgb_img)
        if encoding:
            encodings.append(encoding[0])
        else:
            return "Error: Could not detect a face in one or more images."
    
    if face_recognition.compare_faces([encodings[0]], encodings[1])[0] and \
       face_recognition.compare_faces([encodings[0]], encodings[2])[0]:
        return "Approved"
    else:
        return "Not Approved"

# Load known faces and create Faiss index
known_encodings, known_names = load_known_faces()
face_index = create_faiss_index(known_encodings) if known_encodings else None

# ------ API Endpoints ------

@app.route("/upload", methods=["POST"])
@jwt_required()
def upload():
    """Authenticated users can upload images to COMPANY/EMPLOYEE."""
    if "image" not in request.files:
        return jsonify({"error": "No image file provided."}), 400
    
    file = request.files["image"]
    username = get_jwt_identity()
    filename = f"{username}.jpg"
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    
    return jsonify({"message": "Image uploaded successfully."})

@app.route("/recognize", methods=["POST"])
@jwt_required()
def recognize():
    if not face_index:
        return jsonify({"error": "No known faces loaded."}), 500
    
    if "image" not in request.files:
        return jsonify({"error": "No image file provided."}), 400
    
    file = request.files["image"]
    np_arr = np.frombuffer(file.read(), np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    
    face_locations, face_names = recognize_faces_faiss(frame, face_index, known_names)
    
    return jsonify({"faces": face_names, "locations": face_locations})

@app.route("/verify_faces", methods=["POST"])
@jwt_required()
def verify_faces():
    if "image1" not in request.files or "image2" not in request.files or "image3" not in request.files:
        return jsonify({"error": "Please upload exactly three images."}), 400
    
    image_files = [request.files["image1"], request.files["image2"], request.files["image3"]]
    result = verify_images(image_files)
    return jsonify({"verification_result": result})

if __name__ == "__main__":
    app.run(debug=True)
