import os
import sys
import json
import numpy as np
import cv2

# Ensure we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.db import get_db_connection
from app.services.face_service import face_service

app = create_app()

def migrate():
    with app.app_context():
        print("Iniciando migración de FotoPerfil a SFace Descriptors...")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT ID, NombreCompleto, FotoPerfil FROM Empleados WHERE EstadoEmpleado = 'Activo' AND FotoPerfil IS NOT NULL")
        empleados = cursor.fetchall()
        
        exitos = 0
        fallos = 0
        
        for emp in empleados:
            try:
                # Build the absolute path to the image
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                # emp.FotoPerfil is usually something like '/static/uploads/faces/face_xxx.jpg'
                rel_path = emp.FotoPerfil.lstrip('/')
                img_path = os.path.join(base_dir, rel_path.replace('/', os.sep))
                
                if not os.path.exists(img_path):
                    print(f"[{emp.ID}] {emp.NombreCompleto}: Archivo de foto no encontrado en {img_path}")
                    fallos += 1
                    continue
                    
                # Read image
                img = cv2.imread(img_path)
                if img is None:
                    print(f"[{emp.ID}] {emp.NombreCompleto}: No se pudo leer la imagen")
                    fallos += 1
                    continue
                    
                height, width, _ = img.shape
                face_service.detector.setInputSize((width, height))
                
                _, faces = face_service.detector.detect(img)
                
                if faces is None or len(faces) == 0:
                    print(f"[{emp.ID}] {emp.NombreCompleto}: SFace no detectó rostros en la foto")
                    fallos += 1
                    continue
                    
                # Align and extract feature
                face = faces[0]
                aligned_face = face_service.recognizer.alignCrop(img, face)
                face_feature = face_service.recognizer.feature(aligned_face)
                
                descriptor = face_feature[0].tolist()
                descriptor_str = json.dumps(descriptor)
                
                # Update database
                cursor.execute("UPDATE Empleados SET FaceDescriptor = ? WHERE ID = ?", descriptor_str, emp.ID)
                conn.commit()
                
                # Update cache
                face_service.actualizar_cache_empleado(emp.ID, descriptor)
                
                print(f"[{emp.ID}] {emp.NombreCompleto}: Migrado exitosamente.")
                exitos += 1
                
            except Exception as e:
                print(f"[{emp.ID}] {emp.NombreCompleto}: Error - {e}")
                fallos += 1
                
        print(f"Migración completada. Éxitos: {exitos}, Fallos: {fallos}")

if __name__ == '__main__':
    migrate()
