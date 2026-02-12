from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Max, Q, Count
from .models import Mensagem
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models.functions import Greatest
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from chat import models

@login_required
def chat_lista(request):
    # Pega a última mensagem enviada POR você e a última enviada PARA você
    usuarios = User.objects.exclude(id=request.user.id).annotate(
        ultima_enviada=Max('enviadas__timestamp', filter=Q(enviadas__destinatario=request.user)),
        ultima_recebida=Max('recebidas__timestamp', filter=Q(recebidas__remetente=request.user))
    ).annotate(
        # Escolhe a maior (mais recente) entre as duas datas
        ultima_interacao=Greatest('ultima_enviada', 'ultima_recebida')
    ).order_by('-ultima_interacao')

    for u in usuarios:
        u.nao_lidas = Mensagem.objects.filter(remetente=u, destinatario=request.user, lida=False).count()
    
    return render(request, 'chat/lista.html', {'usuarios': usuarios})

@login_required
def buscar_mensagens(request, destinatario_id):
    try:
        mensagens = Mensagem.objects.filter(
            (Q(remetente=request.user) & Q(destinatario_id=destinatario_id)) |
            (Q(remetente_id=destinatario_id) & Q(destinatario=request.user))
        ).order_by('timestamp')
            
        data = []
        for m in mensagens:
            url_arquivo = None
            if m.arquivo:
                try: url_arquivo = m.arquivo.url
                except: url_arquivo = None

            data.append({
                'id': m.id,
                'conteudo': m.conteudo or "",
                'remetente_id': m.remetente.id,
                'remetente__username': m.remetente.username,
                'editada': getattr(m, 'editada', False),
                'arquivo_url': url_arquivo,
                'timestamp': m.timestamp.isoformat(), # ADICIONADO PARA O HORÁRIO FUNCIONAR
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
@login_required
def enviar_mensagem(request):
    if request.method == 'POST':
        destinatario_id = request.POST.get('destinatario_id')
        conteudo = request.POST.get('conteudo', '')
        arquivo = request.FILES.get('arquivo') 

        if destinatario_id:
            destinatario = get_object_or_404(User, id=destinatario_id)
            
            # 1. Salva no Banco de Dados
            mensagem = Mensagem.objects.create(
                remetente=request.user,
                destinatario=destinatario,
                conteudo=conteudo,
                arquivo=arquivo
            )

            # 2. Prepara os dados para o Websocket
            channel_layer = get_channel_layer()
            data_payload = {
                'id': mensagem.id,
                'conteudo': mensagem.conteudo,
                'remetente_id': request.user.id,
                'destinatario_id': destinatario.id,
                'remetente__username': request.user.username,
                'arquivo_url': mensagem.arquivo.url if mensagem.arquivo else None,
                'horario': mensagem.timestamp.strftime('%H:%M'),
            }

            # 3. Envia para o grupo do DESTINATÁRIO (para o contato subir no topo dele)
            async_to_sync(channel_layer.group_send)(
                f'user_{destinatario.id}',
                {'type': 'chat_message', 'message': data_payload}
            )

            # 4. Envia para o grupo do REMETENTE (para o contato subir no seu próprio topo)
            async_to_sync(channel_layer.group_send)(
                f'user_{request.user.id}',
                {'type': 'chat_message', 'message': data_payload}
            )

            return JsonResponse({'status': 'sucesso'})
    return JsonResponse({'status': 'erro'}, status=400)

@login_required
def contatos_fragment(request):
    usuarios_list = User.objects.exclude(id=request.user.id)
    usuarios_ordenados = []

    for u in usuarios_list:
        # Busca a última mensagem (enviada ou recebida) entre você e este usuário
        ultima_msg = Mensagem.objects.filter(
            (Q(remetente=request.user) & Q(destinatario=u)) |
            (Q(remetente=u) & Q(destinatario=request.user))
        ).order_by('-timestamp').first()

        # Guarda o timestamp para ordenar depois
        u.timestamp_ordenacao = ultima_msg.timestamp if ultima_msg else None
        
        # Conta as não lidas para o balão vermelho
        u.nao_lidas = Mensagem.objects.filter(
            remetente=u, 
            destinatario=request.user, 
            lida=False
        ).count()
        
        usuarios_ordenados.append(u)

    # Ordena a lista: quem tem a mensagem mais recente (ou timestamp maior) fica no topo
    # Usuários sem mensagens ficam por último
    usuarios_ordenados.sort(
        key=lambda x: x.timestamp_ordenacao.timestamp() if x.timestamp_ordenacao else 0, 
        reverse=True
    )

    return render(request, 'chat/contatos_fragment.html', {'usuarios': usuarios_ordenados})

from django.shortcuts import get_object_or_404

@login_required
def excluir_mensagem(request, mensagem_id):
    # 1. Busca a mensagem ou retorna 404 se não existir
    mensagem = get_object_or_404(Mensagem, id=mensagem_id)
    
    # 2. DEBUG: Imprime no seu terminal para conferir quem é quem
    print(f"DEBUG: Logado: {request.user.id} | Remetente da Msg: {mensagem.remetente.id}")

    # 3. Validação simplificada por ID (mais segura)
    if mensagem.remetente.id == request.user.id:
        mensagem.delete()
        return JsonResponse({'status': 'sucesso'})
    
    # Se chegar aqui, a validação falhou
    return JsonResponse({
        'status': 'erro', 
        'message': 'Você só pode apagar suas próprias mensagens.'
    }, status=403)

@login_required
def editar_mensagem(request, mensagem_id):
    mensagem = get_object_or_404(Mensagem, id=mensagem_id, remetente=request.user)
    if request.method == 'POST':
        novo_conteudo = request.POST.get('conteudo')
        if novo_conteudo and novo_conteudo != mensagem.conteudo:
            mensagem.conteudo = novo_conteudo
            mensagem.editada = True # Marca como editada
            mensagem.save()
            return JsonResponse({'status': 'sucesso'})
    return JsonResponse({'status': 'erro'}, status=400)

@login_required
def marcar_como_lida(request, user_id):
    # Marca como lidas todas as mensagens enviadas pelo 'user_id' para o usuário logado
    Mensagem.objects.filter(
        remetente_id=user_id, 
        destinatario=request.user, 
        lida=False
    ).update(lida=True)
    
    return JsonResponse({'status': 'ok'})

@login_required
def chat_janela_mobile(request, destinatario_id):
    destinatario = get_object_or_404(User, id=destinatario_id)
    return render(request, 'chat/chat_mobile.html', {'destinatario': destinatario})