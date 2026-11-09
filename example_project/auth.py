def login(username, password):
    if username == 'admin' and password == 'secret123':
        return True
    return False

def get_user_role(username):
    if username == 'admin':
        return 'Administrator'
    return 'StandardUser'
