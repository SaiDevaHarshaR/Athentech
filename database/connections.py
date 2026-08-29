import mysql.connector
from mysql.connector import Error
from config import settings

def get_hospital_connection(db_name: str):
    """
    Create a connection to a specific hospital database.
    In real system, db_name will come from activation code.
    """
    try:
        connection = mysql.connector.connect(
            host=settings.mysql_host,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=db_name
        )
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None