"""
DESKTOP LAUNCHER - SISTEMA HAVAIANAS
VERSÃO FINAL - FORÇA MODO DEBUG
"""

import os
import sys
import threading
import time
import socket
import webbrowser
from app import app

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

class FlaskThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True
        self.port = find_free_port()
        
    def run(self):
        # 🔥 FORÇA MODO DEBUG IGUAL AO VSCODE
        os.environ['FLASK_ENV'] = 'development'
        os.environ['FLASK_DEBUG'] = '1'
        app.run(
            host='127.0.0.1',
            port=self.port,
            debug=True,
            use_reloader=False
        )

if __name__ == '__main__':
    print("="*50)
    print("🩴 HAVAIANAS - MODO DESKTOP")
    print("="*50)
    
    flask_thread = FlaskThread()
    flask_thread.start()
    time.sleep(2)
    
    url = f"http://localhost:{flask_thread.port}"
    print(f"🌐 Servidor rodando em: {url}")
    
    # Abre no navegador padrão
    webbrowser.open(url)
    
    print("✅ Sistema aberto no navegador")
    print("🛑 Feche este terminal para encerrar")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Encerrando...")