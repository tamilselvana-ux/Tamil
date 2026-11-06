from django.core.cache import cache

LOCKOUT_SECONDS = 900  # 15-minute lockout after 5 failed attempts
MAX_LOGIN_ATTEMPTS = 5

def get_client_ip(request_or_ip):
    if isinstance(request_or_ip, str):
        return request_or_ip
    x_forwarded_for = request_or_ip.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request_or_ip.META.get('REMOTE_ADDR', '127.0.0.1')
    return ip

def is_login_rate_limited(request_or_ip, max_attempts=MAX_LOGIN_ATTEMPTS, timeout_seconds=LOCKOUT_SECONDS):
    ip = get_client_ip(request_or_ip)
    cache_key = f"login_attempts_{ip}"
    attempts = cache.get(cache_key, 0)
    return attempts >= max_attempts

def increment_login_attempts(request_or_ip, timeout_seconds=LOCKOUT_SECONDS):
    ip = get_client_ip(request_or_ip)
    cache_key = f"login_attempts_{ip}"
    attempts = cache.get(cache_key, 0) + 1
    cache.set(cache_key, attempts, timeout_seconds)
    return attempts

def reset_login_attempts(request_or_ip):
    ip = get_client_ip(request_or_ip)
    cache_key = f"login_attempts_{ip}"
    cache.delete(cache_key)

def check_login_rate_limit(request_or_ip, max_attempts=MAX_LOGIN_ATTEMPTS):
    ip = get_client_ip(request_or_ip)
    cache_key = f"login_attempts_{ip}"
    attempts = cache.get(cache_key, 0)
    if attempts >= max_attempts:
        return False, max_attempts
    return True, max_attempts - attempts

def record_failed_login(request_or_ip, timeout_seconds=LOCKOUT_SECONDS):
    return increment_login_attempts(request_or_ip, timeout_seconds)
