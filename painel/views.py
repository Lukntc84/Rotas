from datetime import date

from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
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
from django.db.models import Max
from rotas.models import Notificacao
from django.contrib.auth.decorators import user_passes_test
from collections import defaultdict


def _is_motoboy(user):
    return user.groups.filter(name="Motoboy").exists()

def _is_operador(user):
    return user.groups.filter(name="Operador").exists()

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
    is_operador = _is_operador(request.user)
    is_admin = request.user.is_staff

    # Operador deve ver rotas (não tratar como loja)
    if is_operador:
        loja_logada = None

    
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
        "is_admin": is_admin,
        "is_operador": is_operador,
        "is_motoboy": is_motoboy,
        "loja_logada": loja_logada,
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
    mode, filt = _get_date_filter(request)

    rotas = (
        Rota.objects.select_related("motoboy")
        .prefetch_related(
            Prefetch("paradas", queryset=Parada.objects.select_related("loja").order_by("ordem")),
            "transferencias",
        )
    )

    # Filtro por data (mesmo padrão do Dashboard)
    if mode == "range":
        start, end = filt
        rotas = rotas.filter(data__range=(start, end))
        periodo_label = f"{start.strftime('%d/%m/%Y')} até {end.strftime('%d/%m/%Y')}"
    elif mode == "all":
        periodo_label = "Todas as rotas"
    elif mode == "multi":
        periodo_label = ", ".join(d.strftime("%d/%m/%Y") for d in (filt or [])) or hoje.strftime("%d/%m/%Y")
        rotas = rotas.filter(data__in=filt)
    else:
        # mode == "day"
        day = (filt or [hoje])[0]
        rotas = rotas.filter(data=day)
        periodo_label = day.strftime("%d/%m/%Y")

    # ✅ Motoboy vê só as rotas dele
    if _is_motoboy(request.user):
        rotas = rotas.filter(motoboy=request.user)

    rotas = rotas.order_by("data", "id")

    context = {
        "rotas": rotas,
        "hoje": hoje,
        "mode": mode,
        "filt": filt,
        "periodo_label": periodo_label,
    }
    return render(request, "painel/rotas_hoje.html", context)


@login_required
@permission_required("rotas.view_rota", raise_exception=True)
def rota_detalhe(request, rota_id):
    rota = get_object_or_404(
        Rota.objects.select_related("motoboy"),
        id=rota_id
    )

    # Se motoboy, só pode ver a própria rota
    if _is_motoboy(request.user) and rota.motoboy_id != request.user.id:
        return HttpResponseForbidden("Você não pode acessar esta rota.")

    paradas = rota.paradas.select_related("loja").order_by("ordem")

    # ✅ Puxa TODAS as transferências dessa rota 1x e agrupa por loja origem/destino
    transfs = list(
        rota.transferencias.select_related("loja_origem", "loja_destino")
        .order_by("-id")
    )

    por_origem = defaultdict(list)
    por_destino = defaultdict(list)

    for t in transfs:
        if t.loja_origem_id:
            por_origem[t.loja_origem_id].append(t)
        if t.loja_destino_id:
            por_destino[t.loja_destino_id].append(t)

    # ✅ Anexa no objeto parada as listas (pra usar direto no template)
    for p in paradas:
        loja_id = p.loja_id

        # pedidos para COLETAR nessa loja
        p.transfs_coletar = por_origem.get(loja_id, [])

        # pedidos para ENTREGAR nessa loja
        p.transfs_entregar = por_destino.get(loja_id, [])

        p.qtd_coletar = len(p.transfs_coletar)
        p.qtd_entregar = len(p.transfs_entregar)

    return render(request, "painel/rota_detalhe.html", {
        "rota": rota,
        "paradas": paradas,
    })

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
    parada = get_object_or_404(
        Parada.objects.select_related("rota", "loja", "rota__motoboy"),
        id=parada_id
    )

    # aceitar só POST para alterar estado
    if request.method != "POST":
        return HttpResponseForbidden("Use POST para marcar como coletado.")

    # permissão (mantém exatamente sua lógica)
    if request.user.has_perm("rotas.change_parada"):
        pode = True
    elif _is_motoboy(request.user) and parada.rota.motoboy_id == request.user.id:
        pode = True
    else:
        pode = False

    if not pode:
        return HttpResponseForbidden("Sem permissão para marcar esta coleta.")

    with transaction.atomic():
        # 1) Marca a parada como coletada
        parada.status = "coletado"

        # Só atualiza collected_at se existir no model
        if hasattr(parada, "collected_at"):
            parada.collected_at = timezone.now()
            parada.save(update_fields=["status", "collected_at"])
        else:
            parada.save(update_fields=["status"])

        # 2) ✅ UX: se a parada foi coletada, todas as transferências dessa ROTA
        # cuja ORIGEM é essa loja e ainda estão pendentes viram "em_transito"
        Transferencia.objects.filter(
            rota=parada.rota,
            loja_origem=parada.loja,
            status="pendente"
        ).update(
            status="em_transito",
            motorista=request.user,              # opcional mas útil
            confirmado_em=timezone.now(),
            confirmado_por=request.user
        )

    messages.success(request, f"{parada.loja.nome} marcada como coletada. Transferências da origem foram atualizadas para Em Trânsito.")
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
                    status="em_rota",
                    created_by=request.user,   
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
                    mensagem=(
                        f"{request.user.username} criou uma rota com {len(lojas_selecionadas)} paradas "
                        f"para hoje ({hoje.strftime('%d/%m')})."
                    )
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

# painel/views.py

@login_required
@permission_required("rotas.view_transferencia", raise_exception=True)
def transferencias_lista(request):
    from django.utils.dateparse import parse_date
    from django.utils import timezone
    from django.db.models import Q

    hoje = timezone.localdate()

    loja_logada = _get_loja_usuario(request.user)
    is_admin = request.user.is_staff
    is_motoboy = _is_motoboy(request.user)
    is_operador = _is_operador(request.user)

    # ✅ NOVO: base é "não entregue"
    # Antes era: rota__isnull=True
    qs = (
        Transferencia.objects
        .select_related("loja_origem", "loja_destino", "rota", "rota__motoboy")
        .exclude(status="entregue")   # <<< TROQUE se o valor do seu status for outro
        .order_by('-criado_em')
    )

    # ===== REGRA DE VISUALIZAÇÃO =====
    if loja_logada and not (is_admin or is_motoboy or is_operador):
        qs = qs.filter(
            Q(loja_origem=loja_logada) |
            Q(loja_destino=loja_logada)
        )

    # ===== FILTRO POR LOJA =====
    loja_id = request.GET.get('loja')
    if loja_id:
        qs = qs.filter(
            Q(loja_origem_id=loja_id) |
            Q(loja_destino_id=loja_id)
        )

    # ===== FILTRO POR TIPO =====
    tamanho = request.GET.get('tamanho')
    if tamanho:
        qs = qs.filter(tamanho_carga=tamanho)

    # ===== FILTRO DE DATA =====
    data = request.GET.get('data')
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')

    if data:
        parsed = parse_date(data)
        if parsed:
            qs = qs.filter(criado_em__date=parsed)
    else:
        inicio = parse_date(data_inicio) if data_inicio else None
        fim = parse_date(data_fim) if data_fim else None

        if inicio and fim:
            qs = qs.filter(criado_em__date__range=(inicio, fim))
        elif inicio:
            qs = qs.filter(criado_em__date__gte=inicio)
        elif fim:
            qs = qs.filter(criado_em__date__lte=fim)

    # ✅ Divide em 2 abas/seções:
    transferencias_disponiveis = qs.filter(rota__isnull=True)
    transferencias_em_rota = qs.filter(rota__isnull=False)

    # micro ajuste do aviso da rota do dia (se quiser manter)
    rota_ativa = None
    if is_motoboy:
        rota_ativa = (
            Rota.objects
            .filter(motoboy=request.user, data=hoje, status__in=["aberta", "em_rota"])
            .order_by("-id")
            .first()
        )

    return render(request, "painel/transferencias_lista.html", {
        "transferencias_disponiveis": transferencias_disponiveis,
        "transferencias_em_rota": transferencias_em_rota,
        "lojas": Loja.objects.filter(ativa=True).order_by('nome'),
        "rota_ativa": rota_ativa,
        "is_motoboy": is_motoboy,   # ✅ ADICIONE ISSO
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

            user_loja = getattr(request.user, "loja_perfil", None)
            if user_loja and not request.user.is_staff:
                t.tipo = "saida"
                t.loja_origem = user_loja

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
@permission_required("rotas.change_transferencia", raise_exception=True)
@require_POST
def transferencia_confirmar_cd(request, pk):
    t = get_object_or_404(Transferencia, pk=pk)

    # Só permite confirmar CD se já foi entregue pelo motoboy
    if t.status != "aguardando_cd":
        messages.error(request, "Esta transferência ainda não está aguardando confirmação do CD.")
        return redirect("painel:transferencia_detalhe", transferencia_id=t.id)

    obs = (request.POST.get("obs") or "").strip()

    t.confirmada_cd = True
    t.confirmada_cd_em = timezone.now()
    t.confirmada_cd_por = request.user
    t.obs_confirmacao_cd = obs

    # ✅ Agora sim finaliza
    t.status = "confirmada"
    t.save(update_fields=[
        "confirmada_cd", "confirmada_cd_em", "confirmada_cd_por",
        "obs_confirmacao_cd", "status"
    ])

    messages.success(request, "Entrada confirmada no CD. Protocolo finalizado!")
    return redirect("painel:transferencia_detalhe", transferencia_id=t.id)



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
    if request.method != "POST":
        return redirect('painel:transferencias_lista')

    ids_selecionados = request.POST.getlist('transferencias_selecionadas')
    if not ids_selecionados:
        return redirect('painel:transferencias_lista')

    hoje = timezone.localdate()

    with transaction.atomic():
        # 1) Pega SOMENTE transferências ainda sem rota (evita duplicar)
        qs_transferencias = (
            Transferencia.objects
            .select_related("loja_origem", "loja_destino")
            .filter(id__in=ids_selecionados, rota__isnull=True)
        )

        # ✅ CONGELA para não “sumir” depois do update
        transferencias = list(qs_transferencias)

        if not transferencias:
            # tudo já estava vinculado em outra rota, ou ids inválidos
            return redirect('painel:transferencias_lista')

        # 2) Se já existe rota do motoboy HOJE aberta/em_rota, reaproveita
        rota_existente = (
            Rota.objects
            .filter(motoboy=request.user, data=hoje, status__in=["aberta", "em_rota"])
            .order_by("-id")
            .first()
        )

        if rota_existente:
            rota = rota_existente
        else:
            # 3) Se não existe, cria nova
            rota = Rota.objects.create(
                nome=f"Rota {timezone.now().strftime('%d/%m %H:%M')}",
                motoboy=request.user,
                status="em_rota",
                created_by=request.user,  # mantém
                data=hoje,                # ✅ importante para aparecer no filtro do dia
            )

        # 4) Vincula todas as transferências à rota escolhida (bulk update)
        ids_para_vincular = [t.id for t in transferencias]
        Transferencia.objects.filter(id__in=ids_para_vincular).update(rota=rota)

        # 5) Garante paradas únicas e cria apenas as que faltarem
        lojas_unicas_em_ordem = {}
        for trans in transferencias:
            if trans.loja_origem_id:
                lojas_unicas_em_ordem[trans.loja_origem.id] = trans.loja_origem
            if trans.loja_destino_id:
                lojas_unicas_em_ordem[trans.loja_destino.id] = trans.loja_destino

        lojas_ids = list(lojas_unicas_em_ordem.keys())

        ja_existem = set(
            Parada.objects
            .filter(rota=rota, loja_id__in=lojas_ids)
            .values_list("loja_id", flat=True)
        )

        ultima_ordem = (
            Parada.objects
            .filter(rota=rota)
            .aggregate(m=Max("ordem"))
            .get("m") or 0
        )

        for loja_id, loja_obj in lojas_unicas_em_ordem.items():
            if loja_id in ja_existem:
                continue
            ultima_ordem += 1
            Parada.objects.create(
                rota=rota,
                loja=loja_obj,
                ordem=ultima_ordem,
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

    # Se já está em trânsito ou além, não precisa re-confirmar
    if transferencia.status != "pendente":
        messages.info(request, "Esta transferência já foi coletada ou está em andamento.")
        return redirect('painel:transferencia_detalhe', transferencia_id=pk)

    transferencia.status = "em_transito"
    transferencia.motorista = request.user
    transferencia.confirmado_em = timezone.now()
    transferencia.confirmado_por = request.user
    transferencia.save(update_fields=["status", "motorista", "confirmado_em", "confirmado_por"])

    messages.success(request, "Carga coletada com sucesso! Status: Em Trânsito.")
    return redirect('painel:transferencia_detalhe', transferencia_id=pk)

@login_required
def confirmar_recebimento(request, pk):
    transferencia = get_object_or_404(Transferencia, pk=pk)

    if transferencia.status != 'em_transito':
        messages.error(request, "Ação negada: A carga precisa ser coletada antes de ser entregue.")
        return redirect('painel:transferencia_detalhe', transferencia_id=transferencia.id)

    # ✅ Aqui NÃO finaliza. Só marca que foi entregue pelo motoboy e aguarda CD.
    transferencia.status = "aguardando_cd"
    transferencia.confirmado_em = timezone.now()
    transferencia.confirmado_por = request.user
    transferencia.save(update_fields=["status", "confirmado_em", "confirmado_por"])

    messages.success(request, "Entrega registrada. Aguardando confirmação de entrada no CD.")
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

@login_required
@require_POST
def bulk_confirmar_coleta(request, rota_id):
    """
    Confirma coleta em lote:
    pendente -> em_transito
    """
    rota = get_object_or_404(Rota, id=rota_id)

    # segurança: motoboy só mexe na própria rota
    if _is_motoboy(request.user) and rota.motoboy_id != request.user.id:
        return JsonResponse({"ok": False, "error": "Sem permissão."}, status=403)

    ids = request.POST.getlist("ids[]") or request.POST.getlist("ids")
    if not ids:
        return JsonResponse({"ok": False, "error": "Nenhum ID enviado."}, status=400)

    now = timezone.now()

    with transaction.atomic():
        qs = Transferencia.objects.filter(
            id__in=ids,
            rota=rota,
            status="pendente"
        )

        total = qs.count()

        qs.update(
            status="em_transito",
            motorista=request.user,
            confirmado_em=now,
            confirmado_por=request.user
        )

    return JsonResponse({"ok": True, "updated": total})


@login_required
@require_POST
def bulk_confirmar_entrega(request, rota_id):
    """
    Confirma entrega em lote:
    em_transito -> aguardando_cd
    """
    rota = get_object_or_404(Rota, id=rota_id)

    # segurança: motoboy só mexe na própria rota
    if _is_motoboy(request.user) and rota.motoboy_id != request.user.id:
        return JsonResponse({"ok": False, "error": "Sem permissão."}, status=403)

    ids = request.POST.getlist("ids[]") or request.POST.getlist("ids")
    if not ids:
        return JsonResponse({"ok": False, "error": "Nenhum ID enviado."}, status=400)

    now = timezone.now()

    with transaction.atomic():
        qs = Transferencia.objects.filter(
            id__in=ids,
            rota=rota,
            status="em_transito"
        )

        total = qs.count()

        qs.update(
            status="aguardando_cd",
            confirmado_em=now,
            confirmado_por=request.user
        )

    return JsonResponse({"ok": True, "updated": total})