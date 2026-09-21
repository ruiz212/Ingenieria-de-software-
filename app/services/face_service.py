import base64
import json
import logging
import numpy as np
import cv2
import os
from app.db import get_db_connection

logger = logging.getLogger(__name__)

class FaceRecognitionService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FaceRecognitionService, cls).__new__(cls)
            cls._instance.encodings_cache = {}  # {empleado_id: numpy_array}
            cls._instance._cache_loaded = False
            
            # Rutas de los modelos ONNX
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            model_dir = os.path.join(base_dir, 'static', 'models')
            det_model_path = os.path.join(model_dir, 'face_detection_yunet.onnx')
            rec_model_path = os.path.join(model_dir, 'face_recognition_sface.onnx')
            
            # Inicializamos OpenCV YuNet (Detector) y SFace (Reconocedor)
            try:
                # Los parámetros por defecto de YuNet
                cls._instance.detector = cv2.FaceDetectorYN.create(
                    det_model_path, "", (320, 320), 0.9, 0.3, 5000
                )
                cls._instance.recognizer = cv2.FaceRecognizerSF.create(
                    rec_model_path, ""
                )
            except Exception as e:
                logger.error(f"Error cargando modelos OpenCV ONNX: {e}. Asegúrate de que existan en static/models/")
                
        return cls._instance

    def cargar_cache_desde_db(self):
        """Carga en memoria RAM todos los descriptores válidos de la base de datos."""
        if self._cache_loaded:
            return
            
        logger.info("Iniciando carga de descriptores faciales en caché...")
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT ID, FaceDescriptor FROM Empleados "
                "WHERE EstadoEmpleado = 'Activo' AND FaceDescriptor IS NOT NULL"
            )
            count = 0
            for row in cursor.fetchall():
                try:
                    # El FaceDescriptor se asume guardado como una lista JSON
                    descriptor_list = json.loads(row.FaceDescriptor)
                    if isinstance(descriptor_list, list) and len(descriptor_list) == 128:
                        # SFace requiere float32 shape(1, 128)
                        desc_array = np.array([descriptor_list], dtype=np.float32)
                        self.encodings_cache[row.ID] = desc_array
                        count += 1
                except Exception as e:
                    logger.warning(f"Error parseando descriptor del empleado {row.ID}: {e}")
            self._cache_loaded = True
            logger.info(f"Caché de reconocimiento facial cargada con {count} empleados.")
        except Exception as e:
            logger.error(f"Error al cargar caché desde DB: {e}")
        finally:
            conn.close()

    def decodificar_base64_a_numpy(self, base64_str):
        """Convierte un string base64 a un array NumPy (BGR) para OpenCV."""
        try:
            if ',' in base64_str:
                base64_str = base64_str.split(',')[1]
                
            img_bytes = base64.b64decode(base64_str)
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            
            # cv2.imdecode lee nativamente en formato BGR (que es el requerido por OpenCV YuNet y SFace)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            return img
        except Exception as e:
            logger.error(f"Error decodificando imagen base64: {e}")
            return None

    def procesar_imagen_registro(self, image_file):
        """Valida un archivo de imagen, extrae el descriptor (SFace) y lo retorna."""
        try:
            # Leer imagen de request.files (Flask)
            img_bytes = image_file.read()
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            
            if img is None:
                return {"status": "error", "message": "Formato de imagen inválido."}
                
            # Ajustar el tamaño de entrada del detector a las dimensiones de esta imagen
            height, width, _ = img.shape
            self.detector.setInputSize((width, height))
            
            # Detectar caras
            _, faces = self.detector.detect(img)
            
            if faces is None or len(faces) == 0:
                return {"status": "error", "message": "No se detectó ningún rostro en la imagen."}
            if len(faces) > 1:
                return {"status": "error", "message": "Se detectó más de un rostro en la imagen. Usa una foto individual."}
                
            # Alinear cara y extraer feature (descriptor de 128-d)
            face = faces[0]
            aligned_face = self.recognizer.alignCrop(img, face)
            face_feature = self.recognizer.feature(aligned_face)
            
            # Extraer el descriptor de 128 dimensiones y enviarlo como lista plana
            descriptor = face_feature[0].tolist()
            return {"status": "success", "descriptor": descriptor}
        except Exception as e:
            logger.error(f"Error procesando imagen para registro: {e}")
            return {"status": "error", "message": f"Error procesando imagen: {str(e)}"}

    def procesar_imagen_registro_base64(self, base64_str):
        """Valida un string base64, extrae el descriptor (SFace) y lo retorna."""
        try:
            img = self.decodificar_base64_a_numpy(base64_str)
            if img is None:
                return {"status": "error", "message": "Formato de imagen inválido."}
                
            height, width, _ = img.shape
            self.detector.setInputSize((width, height))
            
            _, faces = self.detector.detect(img)
            
            if faces is None or len(faces) == 0:
                return {"status": "error", "message": "No se detectó ningún rostro en la imagen."}
            if len(faces) > 1:
                return {"status": "error", "message": "Se detectó más de un rostro en la imagen. Usa una foto individual."}
                
            face = faces[0]
            aligned_face = self.recognizer.alignCrop(img, face)
            face_feature = self.recognizer.feature(aligned_face)
            
            descriptor = face_feature[0].tolist()
            return {"status": "success", "descriptor": descriptor}
        except Exception as e:
            logger.error(f"Error procesando imagen base64 para registro: {e}")
            return {"status": "error", "message": f"Error procesando imagen: {str(e)}"}

    def actualizar_cache_empleado(self, empleado_id, descriptor_list):
        """Actualiza la memoria RAM con el nuevo descriptor tras un registro."""
        self.encodings_cache[int(empleado_id)] = np.array([descriptor_list], dtype=np.float32)
        logger.info(f"Caché actualizada para empleado ID {empleado_id}")

    def reconocer_rostro(self, base64_img, tolerancia=0.50):
        """
        Recibe una imagen base64, encuentra rostros, y busca coincidencias en caché usando SFace.
        Para SFace usando Distancia Coseno (FR_COSINE), el valor devuelto es la SIMILITUD.
        Mayor valor = mayor similitud. El umbral recomendado por OpenCV es 0.363, pero para
        entornos de producción y seguridad, usaremos 0.50 (tolerancia más estricta).
        """
        if not self._cache_loaded:
            self.cargar_cache_desde_db()
            
        if not self.encodings_cache:
            return {"status": "error", "message": "No hay descriptores cargados en el sistema."}

        img = self.decodificar_base64_a_numpy(base64_img)
        if img is None:
            return {"status": "error", "message": "Imagen corrupta o formato inválido."}

        height, width, _ = img.shape
        self.detector.setInputSize((width, height))
        
        _, faces = self.detector.detect(img)

        if faces is None or len(faces) == 0:
            return {"status": "no_face"}

        # Asumimos que solo nos interesa la cara más grande/principal en el kiosco
        face = faces[0]
        aligned_face = self.recognizer.alignCrop(img, face)
        encoding_a_buscar = self.recognizer.feature(aligned_face)

        mejor_id = None
        mejor_similitud = -1.0  # La similitud coseno va de -1 a 1. Empezamos en lo más bajo.

        # Buscar el match más cercano (MAYOR similitud coseno)
        for emp_id, desc_conocido in self.encodings_cache.items():
            # cv2.FaceRecognizerSF_FR_COSINE = 1
            similitud = self.recognizer.match(desc_conocido, encoding_a_buscar, cv2.FaceRecognizerSF_FR_COSINE)
            
            if similitud > mejor_similitud:
                mejor_similitud = similitud
                mejor_id = emp_id

        # Si la mayor similitud es mayor o igual a la tolerancia, es la persona correcta
        if mejor_similitud >= tolerancia and mejor_id is not None:
            logger.info(f"Match exitoso: ID {mejor_id} con similitud {mejor_similitud}")
            return {"status": "match", "empleado_id": mejor_id, "similitud": float(mejor_similitud)}

        return {"status": "unknown"}

# Inicializamos el singleton automáticamente al cargar el módulo
face_service = FaceRecognitionService()
