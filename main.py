import numpy as np
import socket
from perfilometro_sdk import connect, read_profile  # Módulo hipotético del SDK

# Configuración
PERFILOMETRO_IP = '192.168.1.100'
COBOT_IP = '192.168.1.200'
UMBRAL_TOLERANCIA = 0.5  # en mm

# Cargar perfil de referencia
perfil_maestro = np.loadtxt('perfil_maestro.csv', delimiter=',')

def comparar_perfiles(perfil_actual, perfil_maestro):
    """Compara el perfil actual con el maestro y detecta defectos."""
    diferencias = np.abs(perfil_actual - perfil_maestro)
    if np.max(diferencias) > UMBRAL_TOLERANCIA:
        return True  # Defecto encontrado
    return False

def main():
    """Bucle principal de inspección."""
    perfilometro = connect(PERFILOMETRO_IP)
    cobot_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cobot_socket.connect((COBOT_IP, 30002)) # Puerto por defecto de UR

    print("Sistemas conectados. Listo para inspección.")

    while True:
        # 1. Esperar señal del cobot
        print("Esperando nueva pieza...")
        cobot_socket.recv(1024) # Espera un mensaje del cobot

        # 2. Adquirir perfil
        perfil_actual = read_profile(perfilometro)

        # 3. Analizar perfil
        defecto = comparar_perfiles(perfil_actual, perfil_maestro)

        # 4. Decidir y enviar comando al cobot
        if defecto:
            print("Pieza defectuosa. Enviando comando al cobot.")
            cobot_socket.sendall(b'SEND_TO_ERROR_AREA\n')
        else:
            print("Pieza OK. Enviando comando al cobot.")
            cobot_socket.sendall(b'SEND_TO_GOOD_AREA\n')

