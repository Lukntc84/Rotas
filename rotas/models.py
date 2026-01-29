from django.conf import settings
from django.db import models
from django.utils import timezone

class Loja(models.Model):
    # Novo campo para o login da loja
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="loja_perfil",
        verbose_name="Usuário de Acesso"
    )
    
    nome = models.CharField(max_length=120)
    cidade = models.CharField(max_length=120)
    uf = models.CharField(max_length=2, default="SP")
    cep = models.CharField(max_length=9, default="00000-000")
    bairro = models.CharField(max_length=120, default="Centro")
    numero = models.CharField(max_length=20, default="S/N")
    complemento = models.CharField(max_length=120, blank=True, null=True)
    endereco = models.CharField(max_length=255, default="Rua Exemplo, 123")
    endereco_normalizado = models.CharField(max_length=255, blank=True, null=True)
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    ativa = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nome} - {self.cidade}/{self.uf}"

class Coleta(models.Model):
    STATUS_CHOICES = [
    ("pendente", "Pendente"),
    ("em_transito", "Em Trânsito"), # Motorista coletou
    ("concluido", "Concluído"),    # Loja destino confirmou
    ("cancelado", "Cancelado"),]
    data = models.DateField(default=timezone.now)
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    motorista = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    def __str__(self):
        return f"Coleta {self.loja} - {self.data} ({self.status})"

class Rota(models.Model):
    STATUS_CHOICES = [
        ("aberta", "Aberta"),
        ("em_rota", "Em rota"),
        ("finalizada", "Finalizada"),
    ]
    # Adicionado null=True e blank=True para destravar a migração
    nome = models.CharField(max_length=120, null=True, blank=True)
    data = models.DateField(default=timezone.now)
    motoboy = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="aberta")

    def __str__(self):
        return f"{self.nome} ({self.data})"

class Parada(models.Model):
    # Opções de status
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("coletado", "Coletado"),
    ]

    rota = models.ForeignKey(Rota, on_delete=models.CASCADE, related_name="paradas")
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    ordem = models.IntegerField(default=0)

    # Adicione/Ajuste estes campos:
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    visitado = models.BooleanField(default=False)
    
    # Campo que a view tenta salvar no 'marcar_coletado'
    collected_at = models.DateTimeField(blank=True, null=True) 
    
    # Você já tem esses no seu model anterior, mantenha se desejar:
    data_hora_coleta = models.DateTimeField(blank=True, null=True)
    observacao = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.rota} - {self.loja} (#{self.ordem})"

class Protocolo(models.Model):
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("confirmado", "Confirmado"),
    ]
    # Adicionado null=True e blank=True aqui também
    numero = models.CharField(max_length=30, unique=True, null=True, blank=True)
    tipo = models.CharField(max_length=20, null=True, blank=True)
    data = models.DateField(default=timezone.now)
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name="protocolos", null=True, blank=True)
    responsavel = models.CharField(max_length=120, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    criado_em = models.DateTimeField(auto_now_add=True)
    
    # Campos de confirmação
    confirmado_nome = models.CharField(max_length=100, blank=True, null=True)
    confirmado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="protocolos_confirmados")
    confirmado_em = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.numero}"

class MovimentoEstoque(models.Model):
    TIPO_CHOICES = [("entrada", "Entrada"), ("saida", "Saída")]
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    data = models.DateField(default=timezone.now)
    protocolo = models.CharField(max_length=50, blank=True)

class Transferencia(models.Model):
    
    TAMANHO_CHOICES = [
        ("pequeno", "Pequeno (Motoboy)"),
        ("medio", "Médio (Utilitário)"),
        ("grande", "Grande (Caminhão)"),
    ]
    
    PORTE_CHOICES = [
        ('pequeno', 'Pequeno (Motoboy)'),
        ('grande', 'Grande (Motorista/Carro)'),
    ]
    
    rota = models.ForeignKey(
        Rota, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="transferencias",
        verbose_name="Rota Vinculada"
    )
    
    STATUS_CHOICES = [("pendente", "Pendente"), ("confirmada", "Confirmada")]
    TIPO_CHOICES = [
        ("entrada", "Entrada"), 
        ("saida", "Saída")
    ]

    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, null=True, blank=True)
    
    # --- Campos para Logística (Painel) ---
    motorista = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="transferencias_motorista")
    retirado_por_nome = models.CharField(max_length=120, blank=True, null=True)
    observacao = models.TextField(blank=True, null=True)

    # --- CAMPOS ADICIONAIS PARA GESTÃO (ESTOQUE) ---
    # Adicionando para evitar o FieldError
    nome_produto = models.CharField(max_length=255, blank=True, null=True)
    marca = models.CharField(max_length=100, blank=True, null=True)
    quantidade = models.IntegerField(default=0)
    fornecedor = models.CharField(max_length=255, blank=True, null=True)
    responsavel = models.CharField(max_length=100, blank=True, null=True)
    retirado_por = models.CharField(max_length=100, blank=True, null=True) # Diferente de retirado_por_nome
    data = models.DateField(default=timezone.now)
    numero_documento = models.CharField(max_length=100, blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True) # Com "s" no final
    loja_origem = models.ForeignKey(Loja, on_delete=models.PROTECT, related_name="transf_origem_set", null=True, blank=True)
    loja_destino = models.ForeignKey(Loja, on_delete=models.PROTECT, related_name="transf_destino_set", null=True, blank=True)
    
    numero_transferencia = models.CharField(max_length=50, verbose_name="Nº da Transferência")
    porte_carga = models.CharField(
            max_length=10, 
            choices=PORTE_CHOICES, 
            default='pequeno',
            verbose_name="Porte da Carga"
        )

    # --- Status e Auditoria ---
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="transferencias_criadas")
    confirmado_em = models.DateTimeField(blank=True, null=True)
    confirmado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="transferencias_confirmadas")

    tamanho_carga = models.CharField(
        max_length=10, 
        choices=TAMANHO_CHOICES, 
        default="pequeno"
    )
    
    STATUS_CHOICES = [
        ("pendente", "Pendente"), 
        ("em_transito", "Em Trânsito"),
        ("confirmada", "Confirmada")
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente") #

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.loja} ({self.status})"