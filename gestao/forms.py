# gestao/forms.py
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from rotas.models import Loja, MovimentoEstoque, Protocolo, Transferencia  # ✅ vem do app rotas


# -------------------------
# USUÁRIOS
# -------------------------
ROLE_CHOICES = [
    ("Admin", "Admin"),
    ("Operador", "Operador"),
    ("Motoboy", "Motoboy"),
]

User = get_user_model()


class UsuarioCriarForm(forms.Form):
    username = forms.CharField(max_length=150, label="Usuário")
    email = forms.EmailField(required=False, label="E-mail")
    first_name = forms.CharField(required=False, label="Nome")
    last_name = forms.CharField(required=False, label="Sobrenome")
    is_active = forms.BooleanField(required=False, initial=True, label="Ativo")

# ... outros campos ...
    ROLE_CHOICES = [
        ("Admin", "Admin"),
        ("Operador", "Operador"),
        ("Motoboy", "Motoboy"),
        ("Loja", "Loja"), # Adicione esta linha
    ]
    role = forms.ChoiceField(choices=ROLE_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}))

    password1 = forms.CharField(required=False, widget=forms.PasswordInput, label="Senha")
    password2 = forms.CharField(required=False, widget=forms.PasswordInput, label="Confirmar senha")

    def clean(self):
        cleaned = super().clean()
        p1 = (cleaned.get("password1") or "").strip()
        p2 = (cleaned.get("password2") or "").strip()
        if p1 or p2:
            if p1 != p2:
                self.add_error("password2", "As senhas não coincidem.")
        return cleaned


class UsuarioEditarForm(forms.ModelForm):
    role = forms.ChoiceField(choices=ROLE_CHOICES, label="Grupo")

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "is_active"]
        labels = {
            "username": "Usuário",
            "email": "E-mail",
            "first_name": "Nome",
            "last_name": "Sobrenome",
            "is_active": "Ativo",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        grp = self.instance.groups.first() if self.instance and self.instance.pk else None
        self.fields["role"].initial = grp.name if grp else "Operador"


class UsuarioGrupoForm(forms.Form):
    role = forms.ChoiceField(choices=ROLE_CHOICES, label="Grupo")


# -------------------------
# LOJAS
# -------------------------
class LojaForm(forms.ModelForm):
    class Meta:
        model = Loja
        # ✅ Ajuste conforme seu model Loja atual:
        # no zip, Loja tinha "endereco" e "cidade"
        fields = ["nome", "endereco", "cidade", "ativa"]
        labels = {
            "nome": "Nome",
            "endereco": "Endereço",
            "cidade": "Cidade",
            "ativa": "Ativa",
        }


# -------------------------
# TRANSFERÊNCIAS (entrada/saída por nota)
# -------------------------
UNIDADES = [
    ("Unidade", "Unidade"),
    ("Caixa", "Caixa"),
    ("Pacote", "Pacote"),
    ("Kg", "Kg"),
    ("Litro", "Litro"),
]

class TransferenciaForm(forms.ModelForm):
    # Mantendo a definição de unidade que você já possui
    unidade_medida = forms.ChoiceField(
        choices=UNIDADES, 
        required=False, 
        label="Unidade",
        widget=forms.Select(attrs={"class": "form-control"})
    )

    class Meta:
        model = Transferencia
        fields = [
            "tipo",
            "nome_produto",
            "marca",
            "quantidade",
            "unidade_medida",
            "loja_origem",
            "loja_destino",
            "fornecedor",
            "responsavel",
            "motorista",
            "retirado_por",
            "data",
            "numero_documento",
            "observacoes",
        ]
        widgets = {
            # Adicionando 'form-control' em todos para garantir que apareçam na tela
            "tipo": forms.Select(attrs={"class": "form-control"}),
            "nome_produto": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Cadeira Escritório"}),
            "marca": forms.TextInput(attrs={"class": "form-control"}),
            "quantidade": forms.NumberInput(attrs={"class": "form-control"}),
            "loja_origem": forms.Select(attrs={"class": "form-control"}),
            "loja_destino": forms.Select(attrs={"class": "form-control"}),
            "fornecedor": forms.TextInput(attrs={"class": "form-control"}),
            "responsavel": forms.TextInput(attrs={"class": "form-control"}),
            "motorista": forms.Select(attrs={"class": "form-control"}),
            "retirado_por": forms.TextInput(attrs={"class": "form-control"}),
            "data": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "numero_documento": forms.TextInput(attrs={"class": "form-control"}),
            "observacoes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }
        labels = {
            "tipo": "Tipo",
            "nome_produto": "Produto",
            "marca": "Marca",
            "quantidade": "Quantidade",
            "loja_origem": "Loja origem",
            "loja_destino": "Loja destino",
            "fornecedor": "Fornecedor",
            "responsavel": "Responsável",
            "motorista": "Motorista",
            "retirado_por": "Retirado por",
            "numero_documento": "Nº Documento (NF)",
            "observacoes": "Observações",
        }

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo")
        origem = cleaned.get("loja_origem")
        destino = cleaned.get("loja_destino")

        # Validação lógica de logística
        if tipo == "cd_para_loja" and not destino:
            self.add_error("loja_destino", "Selecione a loja de destino.")
        if tipo == "loja_para_cd" and not origem:
            self.add_error("loja_origem", "Selecione a loja de origem.")

        return cleaned

class ProtocoloForm(forms.ModelForm):
    class Meta:
        model = Protocolo
        fields = ['loja', 'status']

class ProtocoloConfirmarForm(forms.Form):
    confirmado_nome = forms.CharField(max_length=100, label="Nome de quem recebeu")

class MovimentoEstoqueForm(forms.ModelForm):
    class Meta:
        model = MovimentoEstoque
        fields = ['data', 'protocolo']