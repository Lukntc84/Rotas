from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.chat_lista, name='lista'),
    path('buscar/<int:destinatario_id>/', views.buscar_mensagens, name='buscar'),
    path('enviar/', views.enviar_mensagem, name='enviar'),
    path('contatos-fragment/', views.contatos_fragment, name='contatos_fragment'),
    path('excluir/<int:mensagem_id>/', views.excluir_mensagem, name='excluir_mensagem'),
    path('editar/<int:mensagem_id>/', views.editar_mensagem, name='editar_mensagem'),
    path('marcar-lida/<int:user_id>/', views.marcar_como_lida, name='marcar_lida'),
    path('chat/m/<int:destinatario_id>/', views.chat_janela_mobile, name='chat_mobile_room'),
]