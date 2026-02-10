from .models import Mensagem

def contador_mensagens(request):
    if request.user.is_authenticated:
        contagem = Mensagem.objects.filter(destinatario=request.user, lida=False).count()
        return {'mensagens_nao_lidas': contagem > 0}
    return {'mensagens_nao_lidas': False}