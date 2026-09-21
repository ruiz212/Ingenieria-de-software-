import urllib.request
import os

models_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'models')
os.makedirs(models_dir, exist_ok=True)

yunet_url = 'https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx'
sface_url = 'https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx'

print("Descargando YuNet...")
urllib.request.urlretrieve(yunet_url, os.path.join(models_dir, 'face_detection_yunet.onnx'))

print("Descargando SFace...")
urllib.request.urlretrieve(sface_url, os.path.join(models_dir, 'face_recognition_sface.onnx'))

print("Modelos descargados exitosamente en static/models/")
