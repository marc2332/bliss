import pytest
from bliss.config.conductor import client, connection

@pytest.fixture
def two_clients(beacon):
    conductor_conn = client.get_default_connection()
    conductor_conn.set_client_name("test1")
    client._default_connection = None  # force making a new connection
    conductor_conn2 = client.get_default_connection()
    conductor_conn2.set_client_name("test2")
    yield conductor_conn, conductor_conn2
    conductor_conn.close()
    conductor_conn2.close()
