from django.contrib.auth.decorators import user_passes_test

def admin_interno_required(view_func):
    def check(user):
        return user.is_authenticated and user.groups.filter(name="AdminInterno").exists()
    return user_passes_test(check)(view_func)
