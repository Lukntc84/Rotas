from django.urls import path
from . import views

app_name = "gestao"

urlpatterns = [
    path("", views.home, name="home"),

    # usuários
    path("usuarios/", views.usuarios_lista, name="usuarios_lista"),
    path("usuarios/novo/", views.usuario_criar, name="usuario_criar"),
    path("usuarios/<int:user_id>/ativar/", views.usuario_toggle_ativo, name="usuario_toggle_ativo"),
    path("usuarios/<int:user_id>/grupo/", views.usuario_trocar_grupo, name="usuario_trocar_grupo"),
    path("usuarios/<int:user_id>/editar/", views.usuario_editar, name="usuario_editar"),
    path("usuarios/<int:user_id>/senha/", views.usuario_definir_senha, name="usuario_definir_senha"),
    path("usuarios/<int:user_id>/enviar-link-senha/", views.usuario_enviar_link_senha, name="usuario_enviar_link_senha"),
    path("usuarios/<int:user_id>/link-senha/", views.usuario_link_senha, name="usuario_link_senha"),

    # lojas
    path("lojas/", views.lojas_lista, name="lojas_lista"),
    path("lojas/nova/", views.loja_nova, name="loja_nova"),
    path("lojas/<int:loja_id>/editar/", views.loja_editar, name="loja_editar"),
    
    # protocolos
    path("protocolos/", views.protocolos_lista, name="protocolos_lista"),
    path("protocolos/novo/", views.protocolo_novo, name="protocolo_novo"),
    path("protocolos/<int:protocolo_id>/confirmar/", views.protocolo_confirmar, name="protocolo_confirmar"),
    
    #transferencia
    path("estoque/entrada/nova/", views.nova_entrada, name="nova_entrada"),
    path("estoque/saida/nova/", views.nova_saida, name="nova_saida"),
    path("transferencias/", views.transferencias_lista, name="transferencias_lista"),
    path("transferencias/nova/", views.transferencia_nova, name="transferencia_nova"),
]
