def nav_permissions(request):
    user = request.user
    if not user.is_authenticated:
        return {"can_view_paletes": False}

    is_motoboy = user.groups.filter(name="Motoboy").exists()

    loja = getattr(user, "loja_perfil", None)
    is_cd = False
    if loja and getattr(loja, "nome", None):
        is_cd = "CD" in loja.nome.upper()

    can_view_paletes = user.is_staff or user.is_superuser or is_motoboy or is_cd

    return {
        "can_view_paletes": can_view_paletes,
        "is_motoboy": is_motoboy,
        "is_cd": is_cd,
    }