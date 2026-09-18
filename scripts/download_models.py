import os
import urllib.request

models_dir = r"C:\Ingenieria de software\panaderia_amada\static\models"
os.makedirs(models_dir, exist_ok=True)

base_url = "https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model/"
files = [
    "tiny_face_detector_model-weights_manifest.json",
    "tiny_face_detector_model-shard1",
    "face_landmark_68_model-weights_manifest.json",
    "face_landmark_68_model-shard1",
    "face_recognition_model-weights_manifest.json",
    "face_recognition_model-shard1",
    "face_recognition_model-shard2"
]

for f in files:
    url = base_url + f
    out_path = os.path.join(models_dir, f)
    print(f"Downloading {f}...")
    try:
        urllib.request.urlretrieve(url, out_path)
        print("Success.")
    except Exception as e:
        print(f"Failed to download {f}: {e}")

print("Done downloading models.")
