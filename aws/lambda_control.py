import os
import json
import psycopg2
from psycopg2 import Error

# Lectura de variables de entorno configuradas en AWS Lambda
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "smartfactory")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")


def lambda_handler(event, context):
    """
    Función Lambda para procesar comandos de control de hardware (LEDs).
    - POST: registra { "led_id": "led1", "state": 1 } en control_commands.
    - GET:  devuelve el último estado de ?led_id=led1.
    """
    # IMPORTANTE: declarar antes del try para que el finally nunca falle
    connection = None
    cursor = None

    # Permitir CORS para Grafana
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST,GET,OPTIONS"
    }

    try:
        # OPTIONS de CORS
        if event.get('httpMethod') == 'OPTIONS':
            return {"statusCode": 200, "headers": cors_headers, "body": ""}

        http_method = event.get('httpMethod', 'POST')

        if http_method == 'GET':
            # Obtener led_id de los parámetros de consulta (?led_id=led1)
            query_params = event.get('queryStringParameters') or {}
            led_id = query_params.get('led_id')
            state = None
            source = None
        else:
            # Extraer el cuerpo de la petición si viene de API Gateway
            if 'body' in event and event['body']:
                payload = json.loads(event['body'])
            else:
                payload = event

            led_id = payload.get('led_id')
            state = payload.get('state')
            source = payload.get('source', 'grafana')

        # Validar led_id
        if led_id is None:
            return {
                "statusCode": 400,
                "headers": cors_headers,
                "body": json.dumps({"message": "Falta el campo requerido: led_id"})
            }

        if led_id not in ['led1', 'led2']:
            return {
                "statusCode": 400,
                "headers": cors_headers,
                "body": json.dumps({"message": f"led_id inválido: '{led_id}'. Valores permitidos: led1, led2"})
            }

        if http_method == 'POST':
            # Validar que state sea 0 o 1
            if state is None:
                return {
                    "statusCode": 400,
                    "headers": cors_headers,
                    "body": json.dumps({"message": "Falta el campo requerido para POST: state"})
                }
            if int(state) not in [0, 1]:
                return {
                    "statusCode": 400,
                    "headers": cors_headers,
                    "body": json.dumps({"message": "state inválido. Valores permitidos: 0 (apagado), 1 (encendido)"})
                }

        # Conectar a la base de datos PostgreSQL
        connection = psycopg2.connect(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME
        )
        cursor = connection.cursor()

        if http_method == 'GET':
            # Consultar el estado más reciente del LED
            cursor.execute(
                "SELECT state FROM control_commands WHERE led_id = %s ORDER BY command_timestamp DESC LIMIT 1",
                (led_id,)
            )
            row = cursor.fetchone()
            current_state = int(row[0]) if row else 0

            return {
                "statusCode": 200,
                "headers": cors_headers,
                "body": json.dumps({
                    "led_id": led_id,
                    "state": current_state
                })
            }
        else:
            # Insertar el comando en la tabla de control
            insert_query = """
                INSERT INTO control_commands (led_id, state, source)
                VALUES (%s, %s, %s)
            """
            cursor.execute(insert_query, (led_id, int(state), source))
            connection.commit()

            accion = "ENCENDIDO" if int(state) == 1 else "APAGADO"
            print(f">>> COMANDO DE CONTROL REGISTRADO: {led_id.upper()} -> {accion} (Fuente: {source})")

            return {
                "statusCode": 200,
                "headers": cors_headers,
                "body": json.dumps({
                    "message": f"Comando registrado: {led_id} -> {accion}",
                    "led_id": led_id,
                    "state": int(state)
                })
            }

    except (Exception, Error) as error:
        print("Error PostgreSQL en lambda_control:", error)
        return {
            "statusCode": 500,
            "headers": cors_headers,
            "body": json.dumps({"message": "Error interno del servidor"})
        }
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
