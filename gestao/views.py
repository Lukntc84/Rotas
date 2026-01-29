from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from .decorators import admin_interno_required
from .forms import LojaForm, UsuarioCriarForm, UsuarioEditarForm, UsuarioGrupoForm,ProtocoloConfirmarForm, ProtocoloForm, MovimentoEstoqueForm, TransferenciaForm
from rotas.models import Loja, Protocolo
from rotas.models import MovimentoEstoque, Transferencia, Loja, Protocolo
from django.db import transaction
from django.core.exceptions import PermissionDenied

User = get_user_model()


def _set_group(user, role):
    from django.contrib.auth.models import Group
    
    # Se a role vier como 'Admin', mudamos para o grupo que vê tudo
    if role == "Admin":
        group_name = "AdminInterno"
    else:
        group_name = role

    group, created = Group.objects.get_or_create(name=group_name)
    user.groups.clear() # Limpa grupos antigos para não acumular
    user.groups.add(group)


def _send_set_password_link(request, user):
    if not user.email:
        return False

    form = PasswordResetForm({"email": user.email})
    if form.is_valid():
        form.save(
            request=request,
            use_https=False,  # em produção: True
            from_email=None,
            email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
        )
        return True
    return False


@admin_interno_required
def home(request):
    return render(request, "gestao/home.html")


@admin_interno_required
def usuario_link_senha(request, user_id):
    u = get_object_or_404(User, id=user_id)
    uidb64 = urlsafe_base64_encode(force_bytes(u.pk))
    token = default_token_generator.make_token(u)
    path = reverse("password_reset_confirm", kwargs={"uidb64": uidb64, "token": token})
    link = request.build_absolute_uri(path)
    return render(request, "gestao/usuario_link_senha.html", {"u": u, "link": link})


@admin_interno_required
def usuarios_lista(request):
    usuarios = User.objects.all().order_by("username")
    return render(request, "gestao/usuarios_lista.html", {"usuarios": usuarios})


@admin_interno_required
def usuario_criar(request):
    lojas_disponiveis = Loja.objects.filter(usuario__isnull=True).order_by("nome")

    if request.method == "POST":
        form = UsuarioCriarForm(request.POST)
        loja_id = request.POST.get("vincular_loja")
        # Captura o telefone do POST (precisamos que ele esteja no form)
        telefone = request.POST.get("telefone") 

        if form.is_valid():
            try:
                with transaction.atomic():
                    # 1. Cria o usuário
                    user = User.objects.create(
                        username=form.cleaned_data["username"],
                        email=form.cleaned_data.get("email") or "",
                        first_name=form.cleaned_data.get("first_name") or "",
                        last_name=form.cleaned_data.get("last_name") or "",
                        is_active=form.cleaned_data.get("is_active", True),
                    )

                    # 2. Define o grupo
                    role = form.cleaned_data["role"]
                    _set_group(user, role)

                    
                    if role == "Admin":
                        user.is_staff = True     
                        user.is_superuser = True  
                        user.save(update_fields=['is_staff', 'is_superuser'])
                    
                    
                    if telefone:
                        from rotas.models import Perfil # ajuste o import se necessário
                        Perfil.objects.update_or_create(user=user, defaults={'telefone': telefone})

                    # 4. Vincula à Loja se for o caso
                    if role == "Loja" and loja_id:
                        loja = get_object_or_404(Loja, id=loja_id)
                        loja.usuario = user
                        loja.save()

                    # 5. Define a senha (lógica original)
                    p1 = (form.cleaned_data.get("password1") or "").strip()
                    if p1:
                        user.set_password(p1)
                        user.save(update_fields=["password"])
                    else:
                        user.set_unusable_password()
                        user.save(update_fields=["password"])

                    messages.success(request, f"Usuário {user.username} criado com sucesso.")
                    return redirect("gestao:usuarios_lista")
            except Exception as e:
                messages.error(request, f"Erro ao criar usuário: {e}")
    else:
        form = UsuarioCriarForm()

    return render(request, "gestao/usuario_form.html", {
        "form": form, 
        "lojas_disponiveis": lojas_disponiveis
    })

@admin_interno_required
def usuario_editar(request, user_id):
    u = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        form = UsuarioEditarForm(request.POST, instance=u)
        if form.is_valid():
            with transaction.atomic():
                # Salva os dados básicos (User)
                u = form.save()
                _set_group(u, form.cleaned_data["role"])
                
                # Salva o telefone (Perfil)
                from rotas.models import Perfil
                p, _ = Perfil.objects.get_or_create(user=u)
                p.telefone = form.cleaned_data["telefone"]
                p.save()
                
            messages.success(request, "Usuário e telefone atualizados!")
            return redirect("gestao:usuarios_lista")
    else:
        form = UsuarioEditarForm(instance=u)

    return render(request, "gestao/usuario_editar.html", {"form": form, "u": u})

@admin_interno_required
def usuario_definir_senha(request, user_id):
    u = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        form = SetPasswordForm(u, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Senha atualizada para {u.username}.")
            return redirect("gestao:usuarios_lista")
    else:
        form = SetPasswordForm(u)

    return render(request, "gestao/usuario_senha.html", {"form": form, "u": u})


@admin_interno_required
def usuario_enviar_link_senha(request, user_id):
    u = get_object_or_404(User, id=user_id)

    if request.method != "POST":
        return redirect("gestao:usuarios_lista")

    ok = _send_set_password_link(request, u)
    if ok:
        messages.success(request, f"Link de redefinição enviado para {u.email} (ou exibido no console).")
    else:
        messages.error(request, "Não foi possível enviar o link. Verifique se o usuário tem e-mail e se o e-mail está configurado.")
    return redirect("gestao:usuarios_lista")


@admin_interno_required
def usuario_toggle_ativo(request, user_id):
    u = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        u.is_active = not u.is_active
        u.save(update_fields=["is_active"])
        messages.success(request, f"Usuário {u.username} {'ativado' if u.is_active else 'desativado'}.")
    return redirect("gestao:usuarios_lista")


@admin_interno_required
def usuario_trocar_grupo(request, user_id):
    u = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        form = UsuarioGrupoForm(request.POST)
        if form.is_valid():
            role = form.cleaned_data["role"]
            _set_group(u, role)
            messages.success(request, f"Função de {u.username} atualizada para {role}.")
            return redirect("gestao:usuarios_lista")
    else:
        initial_role = u.groups.first().name if u.groups.first() else "Operador"
        form = UsuarioGrupoForm(initial={"role": initial_role})

    return render(request, "gestao/usuario_grupo.html", {"form": form, "u": u})


# ===== LOJAS (sem geolocalização) =====

@admin_interno_required
def lojas_lista(request):
    lojas = Loja.objects.all().order_by("nome")
    return render(request, "gestao/lojas_lista.html", {"lojas": lojas})


@admin_interno_required
def loja_nova(request):
    if request.method == "POST":
        form = LojaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Loja cadastrada com sucesso.")
            return redirect("gestao:lojas_lista")
    else:
        form = LojaForm()

    return render(request, "gestao/loja_form.html", {"form": form})

@admin_interno_required
def loja_editar(request, loja_id):
    loja = get_object_or_404(Loja, id=loja_id)

    if request.method == "POST":
        form = LojaForm(request.POST, instance=loja)
        if form.is_valid():
            form.save()
            messages.success(request, f"Loja '{loja.nome}' atualizada.")
            return redirect("gestao:lojas_lista")
    else:
        form = LojaForm(instance=loja)

    return render(request, "gestao/loja_form.html", {"form": form, "loja": loja})

def is_motoboy(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name__iexact="Motoboy").exists()

@admin_interno_required
def protocolos_lista(request):
    protocolos = Protocolo.objects.select_related("loja").order_by("-criado_em")
    return render(request, "gestao/protocolos_lista.html", {"protocolos": protocolos})

@admin_interno_required
def protocolo_novo(request):
    if request.method == "POST":
        form = ProtocoloForm(request.POST)
        if form.is_valid():
            p = form.save(commit=False)
            p.criado_por = request.user
            p.save()
            messages.success(request, "Protocolo criado.")
            return redirect("gestao:protocolos_lista")
    else:
        form = ProtocoloForm()
    return render(request, "gestao/protocolo_form.html", {"form": form, "titulo": "Novo protocolo"})

@login_required
@user_passes_test(is_motoboy)
def protocolo_confirmar(request, protocolo_id):
    p = get_object_or_404(Protocolo, id=protocolo_id)

    if p.status != Protocolo.Status.PENDENTE:
        messages.info(request, "Esse protocolo já foi finalizado.")
        return redirect("gestao:protocolos_lista")

    if request.method == "POST":
        form = ProtocoloConfirmarForm(request.POST)
        if form.is_valid():
            p.confirmado_nome = form.cleaned_data["confirmado_nome"].strip()
            p.confirmado_por = request.user
            p.confirmado_em = timezone.now()
            p.status = Protocolo.Status.CONFIRMADO
            p.save(update_fields=["confirmado_nome", "confirmado_por", "confirmado_em", "status"])
            messages.success(request, "Protocolo confirmado.")
            return redirect("gestao:protocolos_lista")
    else:
        form = ProtocoloConfirmarForm()

    return render(request, "gestao/protocolo_confirmar.html", {"p": p, "form": form})

@admin_interno_required
def nova_entrada(request):
    if request.method == "POST":
        form = MovimentoEstoqueForm(request.POST, tipo="entrada")
        if form.is_valid():
            mov = form.save(commit=False)
            mov.tipo = MovimentoEstoque.Tipo.ENTRADA
            mov.save()
            messages.success(request, f"Entrada registrada. Protocolo: {mov.protocolo}")
            return redirect("gestao:entradas_lista")  # ou para onde você quiser
    else:
        form = MovimentoEstoqueForm(initial={"data": timezone.localdate()}, tipo="entrada")

    return render(request, "gestao/movimento_form.html", {"form": form, "titulo": "Nova Entrada"})

@admin_interno_required
def nova_saida(request):
    if request.method == "POST":
        form = MovimentoEstoqueForm(request.POST, tipo="saida")
        if form.is_valid():
            mov = form.save(commit=False)
            mov.tipo = MovimentoEstoque.Tipo.SAIDA
            mov.save()
            messages.success(request, f"Saída registrada. Protocolo: {mov.protocolo}")
            return redirect("gestao:saidas_lista")
    else:
        form = MovimentoEstoqueForm(initial={"data": timezone.localdate()}, tipo="saida")

    return render(request, "gestao/movimento_form.html", {"form": form, "titulo": "Nova Saída"})

@login_required
def transferencias_lista(request):
    user = request.user
    

    if user.is_staff:
        qs = Transferencia.objects.all()
    
    # 2. Se for Loja ou Motoboy (ajuste os nomes dos campos conforme seu modelo)
    else:
        qs = Transferencia.objects.filter(usuario=user)

    return render(request, "painel/transferencias_lista.html", {"transferencias": qs})


@login_required
def transferencia_nova(request):
    # Opcional: Impedir motoboy de criar, se desejar
    if request.user.user_type == 'motoboy': 
        raise PermissionDenied

    if request.method == "POST":
        form = TransferenciaForm(request.POST)
        if form.is_valid():
            tr = form.save(commit=False)
            tr.usuario = request.user # Garante que a transferência salve quem a criou
            tr.save()
            messages.success(request, f"Protocolo gerado: {tr.protocolo}")
            return redirect("painel:transferencias_lista")
    else:
        form = TransferenciaForm()

    return render(request, "painel/transferencia_form.html", {"form": form})

@login_required
def transferencia_create(request):
    if request.method == "POST":
        # Aqui você passa o user para o formulário processar os dados
        form = TransferenciaForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            return redirect('painel:transferencias_lista')
    else:
        # Aqui você passa o user para o formulário FILTRAR a lista de lojas
        form = TransferenciaForm(user=request.user)
    
    return render(request, "painel/transferencia_form.html", {"form": form})
