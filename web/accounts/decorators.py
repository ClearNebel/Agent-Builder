from django.core.exceptions import PermissionDenied

def admin_required(function):
    """
    A decorator that checks if a user is in the 'Admins' group.
    """
    def wrap(request, *args, **kwargs):
        if request.user.groups.filter(name='Admins').exists():
            return function(request, *args, **kwargs)
        else:
            raise PermissionDenied
    return wrap