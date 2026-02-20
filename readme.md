# Cola de mensajes

## Para correr la cola de mensajes
Para iniciar la funcionalidad de cola de mensajes correr los siguientes comandos en la carpeta raíz del repositorio:

- Iniciar ambiente virtual:

    `source ./venv/bin/activate`

- Instalar dependencias:

    `pip install -r requirements.txt`

- Correr imagen de redis localmente:
    
    `docker run -d -p 6379:6379 redis:latest`

- Correr cola de mensajes:

    `celery -A monitor-queue.queues worker -l info`

## Configuración de cola de mensajes
La configuración de la cola es la siguiente:
- Nombre para consumo desde microservicio: **registrar_log**
- Apuntamiento (Este sería el consumo a modificar): http://localhost:5002/monitoreo-logs