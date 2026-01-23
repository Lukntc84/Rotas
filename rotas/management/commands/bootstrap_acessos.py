from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from rotas.models import Loja, Coleta, Rota, Parada


class Command(BaseCommand):
    help = "Cria grupos e permissões padrão (Motoboy, Operador, AdminInterno)"

    def handle(self, *args, **options):
        motoboy, _ = Group.objects.get_or_create(name="Motoboy")
        operador, _ = Group.objects.get_or_create(name="Operador")
        admin_int, _ = Group.objects.get_or_create(name="AdminInterno")

        def perms_for(model, actions):
            ct = ContentType.objects.get_for_model(model)
            perms = []
            for act in actions:
                codename = f"{act}_{model._meta.model_name}"
                perms.append(Permission.objects.get(content_type=ct, codename=codename))
            return perms

        # Motoboy: somente leitura
        motoboy.permissions.set(
            perms_for(Loja, ["view"]) +
            perms_for(Coleta, ["view"]) +
            perms_for(Rota, ["view"]) +
            perms_for(Parada, ["view"])
        )

        # Operador: gerencia tudo + pode alterar parada (marcar coletado)
        operador.permissions.set(
            perms_for(Loja, ["add", "change", "delete", "view"]) +
            perms_for(Coleta, ["add", "change", "delete", "view"]) +
            perms_for(Rota, ["add", "change", "delete", "view"]) +
            perms_for(Parada, ["add", "change", "delete", "view"])
        )

        # AdminInterno: gerenciar usuários/grupos/permissões via admin
        # Permissões de auth (User, Group, Permission)
        user_ct = ContentType.objects.get(app_label="auth", model="user")
        group_ct = ContentType.objects.get(app_label="auth", model="group")
        perm_ct = ContentType.objects.get(app_label="auth", model="permission")

        admin_perms = list(Permission.objects.filter(content_type=user_ct)) \
                    + list(Permission.objects.filter(content_type=group_ct)) \
                    + list(Permission.objects.filter(content_type=perm_ct))

        admin_int.permissions.set(admin_perms)

        self.stdout.write(self.style.SUCCESS("Grupos e permissões criados/atualizados com sucesso!"))
