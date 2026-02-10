from django.db import models
from django.contrib.auth.models import User

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