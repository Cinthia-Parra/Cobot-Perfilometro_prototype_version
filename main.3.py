import numpy as np
import socket
import logging
from time import sleep
import json # Usaremos JSON para una configuración más limpia

# --- CONFIGURACIÓN ---
# Modifica estos valores según tu configuración
CONFIG = {
    "perfilometro_ip": "192.168.1.100",
    "perfilometro_port": 23,  # <<< AJUSTAR AQUÍ: Puerto para comandos nativos (Telnet), usualmente es 23.
    "cobot_ip": "192.168.1.200",
    "cobot_port": 30002,
    "perfil_maestro_path": "perfil_maestro.csv",
    "umbral_tolerancia_mm": 0.5
}

# --- Configuración de Logging ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("inspeccion_log.log"),
                        logging.StreamHandler()
                    ])

# --- CLASE DE COMUNICACIÓN CON EL PERFILÓMETRO ---
class CognexPerfilometro:
    """
    Clase real para manejar la conexión y datos del perfilómetro Cognex
    usando comandos nativos TCP/IP.
    """
    def __init__(self, ip_address, port):
        self.ip = ip_address
        self.port = port
        self.socket = None
        self.is_connected = False
        self.connect()

    def connect(self):
        """Establece la conexión por socket con el dispositivo Cognex."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((self.ip, self.port))
            
            # <<< AJUSTAR AQUÍ: Proceso de login.
            # Muchos sistemas Cognex requieren usuario (y a veces contraseña) al conectar.
            # El usuario por defecto suele ser 'admin'. El \r\n es como presionar Enter.
            self.socket.sendall(b'admin\r\n')
            sleep(0.5)
            
            # Leemos la respuesta de bienvenida para limpiar el buffer
            self.socket.recv(2048) 
            
            self.is_connected = True
            logging.info(f"Conexión TCP/IP con Cognex en {self.ip}:{self.port} establecida.")
            return True
        except socket.error as e:
            logging.error(f"Error al conectar con el perfilómetro Cognex: {e}")
            self.is_connected = False
            return False

    def adquirir_perfil(self):
        """
        Envía un comando para adquirir un perfil y procesa la respuesta.
        Esta es la función más importante que debes adaptar.
        """
        if not self.is_connected:
            logging.error("No se puede adquirir perfil, no hay conexión.")
            return None

        try:
            # <<< AJUSTAR AQUÍ: Comando para adquirir datos.
            # Este comando depende de la configuración de tu "Job" en In-Sight.
            # Un ejemplo común es "GetValue" (GV) para leer el resultado de una herramienta.
            # Supongamos que tienes una herramienta llamada 'Perfil' que extrae los datos.
            comando = "GVPerfil\r\n"
            self.socket.sendall(comando.encode('utf-8'))
            
            # --- Recepción de datos ---
            # Los datos pueden llegar en múltiples paquetes.
            respuesta_completa = ""
            while True:
                data = self.socket.recv(4096).decode('utf-8')
                if not data:
                    break
                respuesta_completa += data
                # Los sistemas Cognex suelen terminar su respuesta con \r\n.
                if respuesta_completa.strip().endswith(('0', '1')): # 1=OK, 0=Error
                     break
            
            respuesta_limpia = respuesta_completa.strip()
            logging.debug(f"Respuesta cruda de Cognex: {respuesta_limpia}")

            # <<< AJUSTAR AQUÍ: Lógica para procesar (parsear) la respuesta.
            # El manual debe decir cómo se formatean los datos.
            # Ejemplo: "1\t10.2\t10.3\t10.5..." (código de estado, luego datos separados por tabulador)
            
            partes = respuesta_limpia.split('\t') # Suponiendo que el separador es un tabulador
            
            if partes[0] == '1': # Código de estado 1 significa éxito
                puntos_perfil = np.array(partes[1:], dtype=float)
                logging.info(f"Perfil de {len(puntos_perfil)} puntos recibido correctamente.")
                return puntos_perfil
            else:
                logging.error(f"Cognex reportó un error al adquirir el perfil: {respuesta_limpia}")
                return None

        except socket.timeout:
            logging.warning("Timeout esperando respuesta del perfilómetro.")
            return None
        except Exception as e:
            logging.error(f"Error en adquirir_perfil: {e}")
            return None

    def close(self):
        """Cierra la conexión del socket."""
        if self.socket:
            self.socket.close()
            self.is_connected = False
            logging.info("Conexión con Cognex cerrada.")


# --- CLASE PRINCIPAL DEL SISTEMA DE INSPECCIÓN ---
class SistemaInspeccion:
    """Clase principal para gestionar la conexión y el proceso de inspección."""

    def __init__(self, config):
        self.config = config
        self.perfilometro_ip = config["perfilometro_ip"]
        self.perfilometro_port = config["perfilometro_port"]
        self.cobot_ip = config["cobot_ip"]
        self.cobot_port = config["cobot_port"]
        
        self.perfilometro = None
        self.cobot_socket = None
        
        self.perfil_maestro = self.cargar_perfil_maestro(config["perfil_maestro_path"])
        self.UMBRAL_TOLERANCIA = config["umbral_tolerancia_mm"]

    def cargar_perfil_maestro(self, path):
        """Carga el perfil de referencia desde un archivo."""
        try:
            perfil = np.loadtxt(path, delimiter=',')
            logging.info(f"Perfil maestro cargado desde '{path}'.")
            return perfil
        except IOError:
            logging.error(f"No se pudo cargar el archivo '{path}'. Asegúrate de que existe.")
            return None

    def conectar(self):
        """Intenta conectar con el perfilómetro y el cobot."""
        # Conexión con el perfilómetro
        self.perfilometro = CognexPerfilometro(self.perfilometro_ip, self.perfilometro_port)
        if not self.perfilometro.is_connected:
            return False

        # Conexión con el cobot
        try:
            self.cobot_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.cobot_socket.connect((self.cobot_ip, self.cobot_port))
            self.cobot_socket.settimeout(10)
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
        
        if len(self.perfil_maestro) != len(perfil_actual):
            logging.error(f"Discrepancia de tamaño: Perfil maestro ({len(self.perfil_maestro)} puntos) vs. Perfil actual ({len(perfil_actual)} puntos).")
            return True # Marcar como defecto si los tamaños no coinciden

        # Normalización básica de datos para centrar los perfiles
        perfil_actual_norm = perfil_actual - np.mean(perfil_actual)
        perfil_maestro_norm = self.perfil_maestro - np.mean(self.perfil_maestro)

        diferencias = np.abs(perfil_actual_norm - perfil_maestro_norm)
        desviacion_maxima = np.max(diferencias)

        if desviacion_maxima > self.UMBRAL_TOLERANCIA:
            logging.info(f"DEFECTO DETECTADO. Desviación máxima: {desviacion_maxima:.2f} mm (Umbral: {self.UMBRAL_TOLERANCIA} mm).")
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
                logging.info("Esperando señal de nueva pieza del cobot...")
                data = self.cobot_socket.recv(1024)
                if not data:
                    logging.warning("Conexión con el cobot perdida. Intentando reconectar...")
                    sleep(5)
                    self.conectar_cobot() # Intenta reconectar solo el cobot
                    continue

                logging.info("Señal de nueva pieza recibida. Activando perfilómetro.")
                perfil_actual = self.perfilometro.adquirir_perfil()
                
                if perfil_actual is not None:
                    defecto = self.comparar_perfiles(perfil_actual)
                    
                    if defecto:
                        self.enviar_comando_cobot("PIEZA_DEFECTUOSA\n")
                    else:
                        self.enviar_comando_cobot("PIEZA_BUENA\n")
                else:
                    logging.error("No se recibió perfil del sensor. No se envió comando al cobot.")
                    
            except socket.timeout:
                logging.warning("Timeout esperando señal del cobot. El ciclo continúa...")
            except Exception as e:
                logging.error(f"Error inesperado en el ciclo principal: {e}")
                logging.info("Intentando reiniciar conexiones en 10 segundos...")
                sleep(10)
                self.conectar() # Intenta reconectar todo

    def desconectar_todo(self):
        """Cierra todas las conexiones de forma segura."""
        if self.perfilometro:
            self.perfilometro.close()
        if self.cobot_socket:
            self.cobot_socket.close()
            logging.info("Conexión con cobot cerrada.")


# --- FUNCIÓN PRINCIPAL ---
if __name__ == "__main__":
    sistema = SistemaInspeccion(CONFIG)
    
    if sistema.perfil_maestro is None:
        logging.critical("No se puede iniciar el sistema sin el perfil maestro. Saliendo.")
        exit()
        
    if sistema.conectar():
        logging.info("Sistemas conectados. Iniciando ciclo de inspección...")
        try:
            sistema.ejecutar_ciclo_inspeccion()
        except KeyboardInterrupt:
            logging.info("Programa detenido por el usuario.")
        finally:
            sistema.desconectar_todo()
            logging.info("Sistemas desconectados. Programa finalizado.")
    else:
        logging.critical("Fallo en la conexión inicial. Revisa los logs y la configuración.")
