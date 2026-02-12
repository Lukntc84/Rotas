from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

class Mensagem(models.Model):
    remetente = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enviadas')
    destinatario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recebidas')
    conteudo = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    lida = models.BooleanField(default=False)
    editada = models.BooleanField(default=False)
    arquivo = models.FileField(upload_to='chat_arquivos/', null=True, blank=True)

    class Meta:
        ordering = ['timestamp']
        verbose_name_plural = "Mensagens"

    def __str__(self):
        return f"{self.remetente} -> {self.destinatario}: {self.conteudo[:20]}"
    
@receiver(post_save, sender=Mensagem) # Certifique-se que o nome do model é Mensagem
def enviar_mensagem_websocket(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        # Ordena os IDs para garantir que a sala seja a mesma para os dois
        ids = sorted([instance.remetente.id, instance.destinatario.id])
        room_group_name = f'chat_{ids[0]}_{ids[1]}'

        # Formata os dados exatamente como seu JS espera
        dados_mensagem = {
            'id': instance.id,
            'conteudo': instance.conteudo,
            'remetente_id': instance.remetente.id,
            'remetente__username': instance.remetente.username,
            'arquivo_url': instance.arquivo.url if instance.arquivo else None,
        }

        # Manda para o Channels
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'chat_message', # Isso chama o método chat_message no consumers.py
                'message': dados_mensagem
            }
        )