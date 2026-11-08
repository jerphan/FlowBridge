def send_notification(user, message):
    print(f'Notification sent to {user}: {message}')
    return True

def log_event(event_type, details):
    print(f'LOG [{event_type}]: {details}')
    return True
