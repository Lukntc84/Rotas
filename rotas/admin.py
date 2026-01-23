from django.contrib import admin
from .models import Loja, Rota, Parada, Transferencia
admin.site.register([Loja, Rota, Parada, Transferencia])