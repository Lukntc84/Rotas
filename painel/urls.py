from django.urls import path
from . import views
from django.urls import path, include

app_name = "painel"

urlpatterns = [
    path("", views.home, name="home"),
    path("rotas/", views.rotas_hoje, name="rotas_hoje"),
    path("rotas/<int:rota_id>/", views.rota_detalhe, name="rota_detalhe"),
    path("paradas/<int:parada_id>/coletado/", views.marcar_coletado, name="marcar_coletado"),
    path("rotas/<int:rota_id>/adicionar-loja/", views.adicionar_loja_rota, name="adicionar_loja_rota"),
    path("rotas/nova/", views.criar_rota, name="criar_rota"),
    path("rotas/<int:rota_id>/reordenar/", views.rota_reordenar, name="rota_reordenar"),
    path("rotas/<int:rota_id>/reordenar/", views.reordenar_paradas, name="reordenar_paradas"),
    path("transferencias/", views.transferencias_lista, name="transferencias_lista"),
    path("transferencias/novo/", views.transferencia_nova, name="transferencia_nova"),
    path("transferencias/<int:transferencia_id>/", views.transferencia_detalhe, name="transferencia_detalhe"),
    path("transferencias/<int:transferencia_id>/confirmar/", views.transferencia_confirmar, name="transferencia_confirmar"),
    path('transferencias/<int:transferencia_id>/excluir/', views.transferencia_excluir, name='transferencia_excluir'),
    path('transferencias/criar-rota/', views.criar_rota_motorista, name='criar_rota_motorista'),
    path('transferencia/<int:pk>/coletar/', views.confirmar_coleta, name='confirmar_coleta'),
    path('transferencia/<int:pk>/receber/', views.confirmar_recebimento, name='confirmar_recebimento'),
]
