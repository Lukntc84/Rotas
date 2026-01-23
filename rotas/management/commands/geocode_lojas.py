from django.core.management.base import BaseCommand
from rotas.models import Loja

class Command(BaseCommand):
    help = "Geocodifica lojas que não têm lat/lng"

    def handle(self, *args, **options):
        total = 0
        for loja in Loja.objects.all():
            if loja.endereco and (loja.lat is None or loja.lng is None):
                loja.save()  # vai chamar o save() do model e geocodificar
                total += 1
                self.stdout.write(self.style.SUCCESS(f"OK: {loja.nome} -> {loja.lat},{loja.lng}"))
        self.stdout.write(self.style.WARNING(f"Concluído. Lojas atualizadas: {total}"))
