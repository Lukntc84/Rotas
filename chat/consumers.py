import json
from channels.generic.websocket import AsyncWebsocketConsumer

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.meu_id = self.scope['user'].id
        # Usamos o grupo do usuário logado para centralizar tudo (mensagens e notificações)
        self.user_group = f'user_{self.meu_id}'

        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.user_group, self.channel_name)

    # ESSA FUNÇÃO É ESSENCIAL: Ela recebe o sinal da View e envia para o JS
    async def chat_message(self, event):
        message = event['message']
        await self.send(text_data=json.dumps(message))