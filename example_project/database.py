def connect_db(db_name):
    print('Connecting to database:', db_name)
    connection_active = True
    return connection_active

def query_records(table):
    if table == 'orders':
        return [{'id': 101, 'amount': 150.0, 'tier': 'gold'}, {'id': 102, 'amount': 80.0, 'tier': 'silver'}]
    return []
