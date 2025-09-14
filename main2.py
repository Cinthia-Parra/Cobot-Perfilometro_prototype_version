import numpy as np
import socket
import logging
from time import sleep

# Importa el SDK del perfilómetro. Esto es un módulo ficticio.
# En un proyecto real, tendrías que usar el SDK proporcionado por el fabricante del sensor.
try:
    from perfilometro_sdk import Perfilometro  # Clase para manejar la conexión y datos del perfilómetro
except ImportError:
    logging.error("Error: El módulo 'perfilometro_sdk' no se encontró. Asegúrate de tener el SDK del fabricante instalado.")
    exit()

# --- Configuración global ---
# Usa logging para registrar eventos en un archivo. Es mucho mejor que usar print().
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("inspeccion_log.log"),
                        logging.StreamHandler()
                    ])

class SistemaInspeccion:
    """Clase principal para gestionar la conexión y el proceso de inspección."""

    def __init__(self, perfilometro_ip, cobot_ip, cobot_port=30002):
        """Inicializa las IPs y puertos, y las conexiones a None."""
        self.perfilometro_ip = perfilometro_ip
        self.cobot_ip = cobot_ip
        self.cobot_port = cobot_port
        self.perfilometro = None
        self.cobot_socket = None
        self.perfil_maestro = self.cargar_perfil_maestro()
        self.UMBRAL_TOLERANCIA = 0.5  # en mm

    def cargar_perfil_maestro(self):
        """Carga el perfil de referencia desde un archivo."""
        try:
            perfil = np.loadtxt('perfil_maestro.csv', delimiter=',')
            logging.info("Perfil maestro cargado correctamente.")
            return perfil
        except IOError:
            logging.error("No se pudo cargar el archivo 'perfil_maestro.csv'. Asegúrate de que existe.")
            return None

    def conectar(self):
        """Intenta conectar con el perfilómetro y el cobot. Maneja excepciones."""
        # Conexión con el perfilómetro
        try:
            self.perfilometro = Perfilometro(self.perfilometro_ip)
            logging.info(f"Conexión con el perfilómetro en {self.perfilometro_ip} establecida.")
        except Exception as e:
            logging.error(f"Error al conectar con el perfilómetro: {e}")
            return False

        # Conexión con el cobot
        try:
            self.cobot_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.cobot_socket.connect((self.cobot_ip, self.cobot_port))
            self.cobot_socket.settimeout(5)  # Establece un tiempo de espera para las operaciones de socket
            logging.info(f"Conexión con el cobot en {self.cobot_ip}:{self.cobot_port} establecida.")
        except socket.error as e:
            logging.error(f"Error al conectar con el cobot: {e}")
            return False
        
        return True

    def comparar_perfiles(self, perfil_actual):
        """Compara el perfil actual con el maestro y detecta defectos."""
        if self.perfil_maestro is None:
            logging.warning("No hay perfil maestro cargado. No se puede realizar la inspección.")
            return None
        
        # Opcional: Normalización básica de datos para centrar los perfiles
        perfil_actual_norm = perfil_actual - np.mean(perfil_actual)
        perfil_maestro_norm = self.perfil_maestro - np.mean(self.perfil_maestro)

        diferencias = np.abs(perfil_actual_norm - perfil_maestro_norm)
        desviacion_maxima = np.max(diferencias)

        if desviacion_maxima > self.UMBRAL_TOLERANCIA:
            logging.info(f"DEFECTO DETECTADO. Desviación máxima: {desviacion_maxima:.2f} mm.")
            return True
        else:
            logging.info(f"Pieza OK. Desviación máxima: {desviacion_maxima:.2f} mm.")
            return False

    def enviar_comando_cobot(self, comando):
        """Envía un comando al cobot de manera segura."""
        try:
            self.cobot_socket.sendall(comando.encode('utf-8'))
            logging.info(f"Comando '{comando.strip()}' enviado al cobot.")
        except socket.error as e:
            logging.error(f"Error al enviar comando al cobot: {e}")

    def ejecutar_ciclo_inspeccion(self):
        """Bucle principal que gestiona el flujo de trabajo."""
        while True:
            try:
                # 1. Esperar señal del cobot (el cobot envía algo para indicar que está listo)
                logging.info("Esperando señal de nueva pieza del cobot...")
                data = self.cobot_socket.recv(1024)
                if not data:
                    logging.warning("Conexión con el cobot perdida. Reintentando en 5s...")
                    sleep(5)
                    self.conectar()
                    continue

                logging.info("Señal de nueva pieza recibida.")

                # 2. Adquirir perfil desde el sensor
                perfil_actual = self.perfilometro.adquirir_perfil()
                
                # 3. Analizar perfil y tomar decisión
                defecto = self.comparar_perfiles(perfil_actual)
                
                # 4. Enviar resultado al cobot
                if defecto:
                    self.enviar_comando_cobot("PIEZA_DEFECTUOSA\n")
                else:
                    self.enviar_comando_cobot("PIEZA_BUENA\n")
                    
            except socket.timeout:
                logging.warning("Tiempo de espera agotado del socket. Reintentando...")
                
            except Exception as e:
                logging.error(f"Error inesperado en el ciclo principal: {e}")
                sleep(5) # Espera antes de reintentar

# --- Función Principal ---
if __name__ == "__main__":
    # Configurar IPs de forma dinámica (simulado con valores fijos por ahora)
    PERFILOMETRO_IP = '192.168.1.100'
    COBOT_IP = '192.168.1.200'

    sistema = SistemaInspeccion(PERFILOMETRO_IP, COBOT_IP)
    
    if sistema.perfil_maestro is None:
        logging.critical("No se puede iniciar el sistema sin el perfil maestro.")
        exit()
        
    if sistema.conectar():
        logging.info("Sistemas conectados. Iniciando ciclo de inspección...")
        sistema.ejecutar_ciclo_inspeccion()
    else:
        logging.critical("No se pudo conectar a los sistemas. Saliendo...")