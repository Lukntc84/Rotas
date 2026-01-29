from datetime import date

from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.http import HttpResponseForbidden
from django.contrib import messages

from rotas.models import Loja, Rota, Parada,Transferencia
from .forms import AdicionarLojaRotaForm, CriarRotaForm, TransferenciaForm
from django.core.exceptions import PermissionDenied
import json
from django.db import transaction
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST

from rotas.models import Notificacao


def _is_motoboy(user):
    return user.groups.filter(name="Motoboy").exists()


def _parse_date(s: str):
    # s no formato YYYY-MM-DD
    try:
        y, m, d = map(int, s.split("-"))
        return date(y, m, d)
    except Exception:
        return None


def _get_date_filter(request):
    mode = request.GET.get("mode", "day")
    hoje = timezone.localdate()

    if mode == "all":
        return mode, None  # sem filtro

    if mode == "range":
        start = _parse_date(request.GET.get("start", ""))
        end = _parse_date(request.GET.get("end", ""))
        if not start or not end:
            return "day", [hoje]

        if end < start:
            start, end = end, start

        return "range", (start, end)


    if mode == "multi":
        raw = request.GET.get("days", "")
        days = [d for d in (_parse_date(x.strip()) for x in raw.split(",")) if d]
        if not days:
            return "day", [hoje]
        return "multi", sorted(set(days))

    # default: day
    day = _parse_date(request.GET.get("day", "")) or hoje
    return "day", [day]


# =========================
# DASHBOARD (HOME)
# =========================
@login_required
def home(request):
    mode, filt = _get_date_filter(request)

    # 1. Queries Base
    rotas_qs = Rota.objects.select_related("motoboy")
    paradas_qs = Parada.objects.select_related("rota", "loja", "rota__motoboy")
    transf_qs = Transferencia.objects.all()

    # 2. IDENTIFICAÇÃO DO USUÁRIO (SEGURANÇA)
    loja_logada = _get_loja_usuario(request.user)
    is_motoboy = _is_motoboy(request.user)
    is_admin = request.user.is_staff
    
    if is_motoboy:
        rotas_qs = rotas_qs.filter(motoboy=request.user)
        paradas_qs = paradas_qs.filter(rota__motoboy=request.user)
        transf_qs = transf_qs.filter(motorista=request.user)
        
    elif loja_logada:
        # ✅ Filtra apenas as transferências da loja
        transf_qs = transf_qs.filter(
            Q(loja_origem=loja_logada) | Q(loja_destino=loja_logada)
        )
        # Limpamos as rotas e paradas para que o operador de loja NÃO as veja
        rotas_qs = Rota.objects.none() 
        paradas_qs = Parada.objects.none()

    # 3. FILTRO POR DATA
    if mode == "range":
        start, end = filt
        if not loja_logada: # Só filtra rotas se não for loja
            rotas_qs = rotas_qs.filter(data__range=(start, end))
            paradas_qs = paradas_qs.filter(rota__data__range=(start, end))
        transf_qs = transf_qs.filter(criado_em__date__range=(start, end))
    elif mode != "all":
        if not loja_logada:
            rotas_qs = rotas_qs.filter(data__in=filt)
            paradas_qs = paradas_qs.filter(rota__data__in=filt)
        transf_qs = transf_qs.filter(criado_em__date__in=filt)

    # 4. CÁLCULOS PARA O DASHBOARD
    total_paradas = paradas_qs.count()
    coletadas = paradas_qs.filter(status="coletado").count()
    
    context = {
        "mode": mode,
        "filt": filt,
        "kpi": {
            # KPIs de logística só terão valores para Admin ou Motoboy
            "total_rotas": rotas_qs.count() if not loja_logada else 0,
            "total_paradas": total_paradas,
            "coletadas": coletadas,
            "pendentes": total_paradas - coletadas,
            "progresso": int((coletadas / total_paradas) * 100) if total_paradas else 0,
            
            # KPIs de transferência (Visíveis para todos)
            "total_transf": transf_qs.count(),
            "entradas": transf_qs.filter(tipo__iexact='entrada').count(),
            "saidas": transf_qs.filter(tipo__iexact='saida').count(),
            "transf_pendentes": transf_qs.exclude(status="confirmada").count(),
        },
        "rotas": rotas_qs.annotate(
            total_lojas=Count("paradas", distinct=True),
            lojas_coletadas=Count("paradas", filter=Q(paradas__status="coletado"), distinct=True),
        ).order_by("data", "id") if not loja_logada else [],
        
        "ultimas_transferencias": transf_qs.order_by("-id")[:5],
        "hoje": timezone.localdate(),
    }
    return render(request, "painel/home.html", context)

# =========================
# ROTAS DE HOJE
# =========================
@login_required
@permission_required("rotas.view_rota", raise_exception=True)
def rotas_hoje(request):
    hoje = timezone.localdate()

    # No seu painel/views.py, ajuste a linha do prefetch:
    rotas = (
        Rota.objects.filter(data=hoje)
        .select_related("motoboy")
        .prefetch_related(
            Prefetch("paradas", queryset=Parada.objects.select_related("loja").order_by("ordem")),
            "transferencias" # Adicione esta linha aqui
        )
    )

    # ✅ Motoboy vê só as rotas dele
    if _is_motoboy(request.user):
        rotas = rotas.filter(motoboy=request.user)

    return render(request, "painel/rotas_hoje.html", {"rotas": rotas, "hoje": hoje})


@login_required
@permission_required("rotas.view_rota", raise_exception=True)
def rota_detalhe(request, rota_id):
    rota = get_object_or_404(Rota.objects.select_related("motoboy"), id=rota_id)

    if _is_motoboy(request.user) and rota.motoboy_id != request.user.id:
        return HttpResponseForbidden("Você não pode acessar esta rota.")

    paradas = rota.paradas.select_related("loja").order_by("ordem")

    # Dentro do loop 'for parada in paradas:' da sua função rota_detalhe
    for parada in paradas:
        # Busca a transferência específica para esta parada
        t_origem = rota.transferencias.filter(loja_origem=parada.loja, status='pendente').first()
        t_transito = rota.transferencias.filter(loja_destino=parada.loja, status='em_transito').first()

        # Anexa o objeto da transferência à parada para usar no HTML
        parada.transf_para_coletar = t_origem
        parada.transf_para_entregar = t_transito

        # Lógica de status visual que você já tem
        if rota.transferencias.filter(loja_origem=parada.loja, status__in=['em_transito', 'confirmada']).exists():
            parada.status_real = "Coletado"
        elif rota.transferencias.filter(loja_destino=parada.loja, status='confirmada').exists():
            parada.status_real = "Entregue"
        else:
            parada.status_real = "Pendente"

    return render(request, "painel/rota_detalhe.html", {"rota": rota, "paradas": paradas})

@login_required
@permission_required("rotas.add_parada", raise_exception=True)  # operador/admin
def adicionar_loja_rota(request, rota_id):
    rota = get_object_or_404(Rota, id=rota_id)

    if request.method == "POST":
        form = AdicionarLojaRotaForm(request.POST)
        if form.is_valid():
            loja = form.cleaned_data["loja"]

            ultima = rota.paradas.order_by("-ordem").first()
            proxima_ordem = (ultima.ordem + 1) if ultima else 1

            Parada.objects.create(
                rota=rota,
                loja=loja,
                ordem=proxima_ordem,
                status="pendente",
            )

            return redirect("painel:rota_detalhe", rota_id=rota.id)
    else:
        form = AdicionarLojaRotaForm()

    return render(request, "painel/adicionar_loja.html", {"rota": rota, "form": form})


# =========================
# MARCAR COLETADO
# =========================
@login_required
def marcar_coletado(request, parada_id):
    parada = get_object_or_404(Parada.objects.select_related("rota"), id=parada_id)

    # aceitar só POST para alterar estado
    if request.method != "POST":
        return HttpResponseForbidden("Use POST para marcar como coletado.")

    # permissão
    if request.user.has_perm("rotas.change_parada"):
        pode = True
    elif _is_motoboy(request.user) and parada.rota.motoboy_id == request.user.id:
        pode = True
    else:
        pode = False

    if not pode:
        return HttpResponseForbidden("Sem permissão para marcar esta coleta.")

    parada.status = "coletado"
    # ⚠️ Só funciona se você tiver esse campo no model Parada
    parada.collected_at = timezone.now()
    parada.save(update_fields=["status", "collected_at"])

    return redirect("painel:rota_detalhe", rota_id=parada.rota_id)


# =========================
# CRIAR ROTA
# =========================
# Certifique-se de que 'transaction' está importado no topo do arquivo:
# from django.db import transaction

@login_required
@permission_required("rotas.add_rota", raise_exception=True)
def criar_rota(request):
    hoje = timezone.localdate()

    if request.method == "POST":
        form = CriarRotaForm(request.POST)
        if form.is_valid():
            motoboy = form.cleaned_data["motoboy"]
            lojas_selecionadas = form.cleaned_data["lojas"]

            with transaction.atomic():
                # 1. Cria a Rota
                rota = Rota.objects.create(
                    data=hoje,
                    motoboy=motoboy,
                    status="aberta"
                )

                # 2. Cria as Paradas Automaticamente
                for index, loja in enumerate(lojas_selecionadas, start=1):
                    Parada.objects.create(
                        rota=rota,
                        loja=loja,
                        ordem=index,
                        status="pendente"
                    )

                # 3. CRIA A NOTIFICAÇÃO PARA O MOTORISTA (Novo passo)
                # Importante: O motorista aqui é o 'motoboy' vindo do formulário
                Notificacao.objects.create(
                    usuario=motoboy,
                    titulo="Nova Rota Atribuída! 🚚",
                    mensagem=f"Você recebeu uma nova rota com {len(lojas_selecionadas)} paradas para hoje ({hoje.strftime('%d/%m')})."
                )

            messages.success(request, f"Rota criada com {len(lojas_selecionadas)} paradas e motorista notificado!")
            return redirect("painel:rota_detalhe", rota_id=rota.id)
    else:
        form = CriarRotaForm()

    return render(request, "painel/criar_rota.html", {"form": form, "hoje": hoje})

@login_required
@require_POST
def rota_reordenar(request, rota_id):
    rota = get_object_or_404(Rota, id=rota_id)

    e_dono = (rota.motoboy == request.user)
    tem_perm = request.user.has_perm("rotas.change_parada") or request.user.has_perm("rotas.change_rota")

    if not (tem_perm or e_dono):
        return JsonResponse({"ok": False, "error": "Sem permissão para ordenar."}, status=403)

    data = json.loads(request.body.decode("utf-8"))
    ids = data.get("ids", [])

    # garante que só reordena paradas dessa rota
    paradas = list(Parada.objects.filter(rota_id=rota_id, id__in=ids))
    if len(paradas) != len(ids):
        return JsonResponse({"ok": False, "error": "Lista inválida."}, status=400)

    with transaction.atomic():
        for ordem, parada_id in enumerate(ids, start=1):
            Parada.objects.filter(id=parada_id, rota_id=rota_id).update(ordem=ordem)

    return JsonResponse({"ok": True})

@login_required
@permission_required("rotas.change_parada", raise_exception=True)  # operador/admin
def reordenar_paradas(request, rota_id):
    if request.method != "POST":
        return HttpResponseForbidden("Use POST.")

    rota = get_object_or_404(Rota, id=rota_id)

    try:
        payload = json.loads(request.body.decode("utf-8"))
        ids = payload.get("ids", [])
        if not isinstance(ids, list) or not ids:
            return JsonResponse({"ok": False, "error": "Lista inválida."}, status=400)
    except Exception:
        return JsonResponse({"ok": False, "error": "JSON inválido."}, status=400)

    # garante que todas as paradas pertencem à rota
    qs = Parada.objects.filter(rota_id=rota.id, id__in=ids)
    if qs.count() != len(ids):
        return JsonResponse({"ok": False, "error": "IDs não pertencem à rota."}, status=400)

    # atualiza ordem (1..n)
    paradas_map = {p.id: p for p in qs}
    for i, pid in enumerate(ids, start=1):
        paradas_map[pid].ordem = i

    with transaction.atomic():
        Parada.objects.bulk_update(paradas_map.values(), ["ordem"])

    return JsonResponse({"ok": True})

def _is_motoboy(user):
    return user.groups.filter(name="Motoboy").exists()

@login_required
@permission_required("rotas.view_transferencia", raise_exception=True)
def transferencias_lista(request):
    # Base: apenas transferências que ainda não estão em rota
    transferencias = Transferencia.objects.filter(rota__isnull=True).order_by('-criado_em')

    # Filtro automático para Motoboys (Ponto 4)
    if _is_motoboy(request.user):
        transferencias = transferencias.filter(tamanho_carga="pequeno")

    # Filtros via URL (para o Operador usar no Painel)
    tamanho = request.GET.get('tamanho')
    status = request.GET.get('status')
    
    if tamanho:
        transferencias = transferencias.filter(tamanho_carga=tamanho)
    if status:
        transferencias = transferencias.filter(status=status)

    return render(request, "painel/transferencias_lista.html", {
            "transferencias": transferencias,
            "lojas": Loja.objects.filter(ativa=True).order_by('nome'), # ESTA LINHA É ESSENCIAL
        })

@login_required
@permission_required("rotas.add_transferencia", raise_exception=True)
def transferencia_nova(request):
    if request.method == "POST":
        # PASSE O USER AQUI NO POST
        form = TransferenciaForm(request.POST, user=request.user)
        if form.is_valid():
            t = form.save(commit=False)
            t.criado_por = request.user
            t.status = "pendente"
            t.save()
            messages.success(request, f"Transferência criada com sucesso!") 
            return redirect("painel:transferencias_lista")
    else:
        # PASSE O USER AQUI NO GET (Isso trava a lista na tela)
        form = TransferenciaForm(user=request.user)

    return render(request, "painel/transferencia_form.html", {"form": form})

@login_required
@permission_required("rotas.view_transferencia", raise_exception=True)
def transferencia_detalhe(request, transferencia_id):
    t = get_object_or_404(
        Transferencia.objects.select_related("loja", "motorista", "criado_por", "confirmado_por"),
        id=transferencia_id,
    )

    # ✅ Lógica para editar 'retirado_por' antes de confirmar
    if request.method == "POST" and "atualizar_retirado" in request.POST:
        if t.status != "confirmada":
            t.retirado_por = request.POST.get("retirado_por")
            t.save(update_fields=["retirado_por"])
            messages.success(request, "Responsável pela retirada atualizado!")
            return redirect("painel:transferencia_detalhe", transferencia_id=t.id)

    return render(request, "painel/transferencia_detalhe.html", {"t": t})

@login_required
def transferencia_confirmar(request, transferencia_id):
    t = get_object_or_404(Transferencia, id=transferencia_id)

    # regra de permissão existente
    pode = request.user.has_perm("rotas.change_transferencia") or \
           (_is_motoboy(request.user) and t.motorista_id == request.user.id)

    if not pode:
        return HttpResponseForbidden("Sem permissão para confirmar.")

    if request.method != "POST":
        return HttpResponseForbidden("Use POST.")

    if t.status != "confirmada": # ✅ Ajustado para string direta
        t.status = "confirmada"
        t.confirmado_em = timezone.now()
        t.confirmado_por = request.user
        t.save(update_fields=["status", "confirmado_em", "confirmado_por"])

    return redirect("painel:transferencia_detalhe", transferencia_id=t.id)

from django.contrib.auth.decorators import user_passes_test


@user_passes_test(lambda u: u.is_superuser)
@login_required
def transferencia_excluir(request, transferencia_id):
    # ✅ Apenas Admin (superuser) pode excluir
    if not request.user.is_superuser:
        return HttpResponseForbidden("Apenas administradores podem excluir transferências.")
    
    t = get_object_or_404(Transferencia, id=transferencia_id)
    if request.method == "POST":
        t.delete()
        messages.success(request, "Transferência excluída permanentemente.")
        return redirect("painel:transferencias_lista")
    
    return HttpResponseForbidden("Método inválido.")

def _is_loja(user):
    return user.groups.filter(name="Loja").exists() or hasattr(user, 'loja_perfil')

@login_required
def paradas_loja(request):
    if not _is_loja(request.user):
        return HttpResponseForbidden("Apenas lojas acessam esta página.")
        
    minha_loja = request.user.loja_perfil
    # Pega todas as paradas daquela loja específica
    paradas = Parada.objects.filter(loja=minha_loja).select_related('rota').order_by('-rota__data')
    
    return render(request, "painel/minhas_paradas.html", {"paradas": paradas})

def _get_loja_usuario(user):
    # Retorna o objeto Loja se o usuário estiver vinculado a uma, senão None
    return getattr(user, 'loja_perfil', None)

@login_required
def minhas_paradas(request):
    loja_logada = _get_loja_usuario(request.user)
    if not loja_logada:
        return HttpResponseForbidden("Apenas lojas acessam esta página.")
        
    # Busca apenas as paradas desta loja em qualquer rota
    paradas = Parada.objects.filter(loja=loja_logada).select_related('rota').order_by('-rota__data')
    
    return render(request, "painel/minhas_paradas.html", {"paradas": paradas})

from django.db import transaction

@login_required
def criar_rota_motorista(request):
    if request.method == "POST":
        ids_selecionados = request.POST.getlist('transferencias_selecionadas')
        
        if not ids_selecionados:
            return redirect('painel:transferencias_lista')

        with transaction.atomic():
            # 1. Cria a Rota
            nova_rota = Rota.objects.create(
                nome=f"Rota {timezone.now().strftime('%d/%m %H:%M')}",
                motoboy=request.user,
                status="em_rota"
            )

            # 2. Busca as transferências selecionadas
            transferencias = Transferencia.objects.filter(id__in=ids_selecionados)
            
            # Usaremos um dicionário para garantir que cada loja seja uma parada única
            lojas_unicas = {}

            for trans in transferencias:
                # Vincula a transferência à rota no banco
                trans.rota = nova_rota
                trans.save()
                
                # Registra as lojas envolvidas para criar as paradas depois
                lojas_unicas[trans.loja_origem.id] = trans.loja_origem
                lojas_unicas[trans.loja_destino.id] = trans.loja_destino

            # 3. CRIA AS PARADAS (Isso preenche o rota.paradas que sua view de detalhe busca)
            for i, (loja_id, loja_obj) in enumerate(lojas_unicas.items()):
                Parada.objects.create(
                    rota=nova_rota,
                    loja=loja_obj,
                    ordem=i + 1,
                    status="pendente"
                )

        return redirect('painel:rotas_hoje')
    
    return redirect('painel:transferencias_lista')

@login_required
def dashboard(request):
    # Se for Admin (Staff), ele vê tudo.
    if request.user.is_staff:
        transferencias = Transferencia.objects.all()
        rotas_ativas = Rota.objects.filter(status="em_rota")
    else:
        # Se for usuário de LOJA, filtramos tudo pela loja vinculada a ele
        user_loja = request.user.loja 
        transferencias = Transferencia.objects.filter(loja=user_loja)
        # Filtra rotas que têm pelo menos uma parada na loja desse usuário
        rotas_ativas = Rota.objects.filter(paradas__loja=user_loja, status="em_rota").distinct()

    context = {
        "total_rotas": rotas_ativas.count(),
        "total_transferencias": transferencias.count(),
        "entradas": transferencias.filter(tipo="entrada").count(),
        "saidas": transferencias.filter(tipo="saida").count(),
        "transferencias_recentes": transferencias.order_by("-criado_em")[:5],
        "rotas_ativas": rotas_ativas,
    }
    
    return render(request, "painel/dashboard.html", context)

@login_required
def coletar_transferencia(request, pk):
    transferencia = get_object_or_404(Transferencia, pk=pk)
    # Apenas o motorista da rota ou staff pode coletar
    transferencia.status = "em_transito"
    transferencia.save()
    messages.success(request, f"Carga {transferencia.id} marcada como Em Trânsito!")
    return redirect('painel:transferencias_lista')


@login_required
def coletar_carga(request, transferencia_id):
    t = get_object_or_404(Transferencia, id=transferencia_id)
    t.status = "em_transito"
    t.motorista = request.user
    t.save(update_fields=['status', 'motorista'])
    messages.success(request, "Carga coletada! Status: Em Trânsito.")
    return redirect('painel:transferencia_detalhe', transferencia_id=t.id)

from django.core.exceptions import PermissionDenied

@login_required
def confirmar_coleta(request, pk):

    is_motorista = request.user.groups.filter(name='Motoboy').exists()
    if not (is_motorista or request.user.is_staff):
        messages.error(request, "Acesso negado: Somente motoristas podem confirmar a coleta.")
        return redirect('painel:transferencia_detalhe', transferencia_id=pk)

    transferencia = get_object_or_404(Transferencia, pk=pk)
    transferencia.status = "em_transito"
    transferencia.save()
    messages.success(request, "Carga coletada com sucesso!")
    return redirect('painel:transferencia_detalhe', transferencia_id=pk)

@login_required
def confirmar_recebimento(request, pk):
    transferencia = get_object_or_404(Transferencia, pk=pk)
    
    if transferencia.status != 'em_transito':
        messages.error(request, "Ação negada: A carga precisa ser coletada antes de ser entregue.")
        return redirect('painel:transferencia_detalhe', transferencia_id=transferencia.id)

    transferencia.status = "confirmada"
    transferencia.save()
    messages.success(request, "Entrega confirmada com sucesso!")
    return redirect('painel:transferencia_detalhe', transferencia_id=transferencia.id)

@login_required
def marcar_notificacao_lida(request, notificacao_id):
    notificacao = get_object_or_404(Notificacao, id=notificacao_id, usuario=request.user)
    notificacao.lida = True
    notificacao.save()
    return redirect('painel:notificacoes_lista') # Ou para a home

# painel/views.py
@login_required
def notificacoes_lista(request):
    notificacoes = request.user.notificacoes.all()
    return render(request, 'painel/notificacoes_lista.html', {'notificacoes': notificacoes})