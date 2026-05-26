from django import forms
from django.contrib.auth.models import User
from rotas.models import Loja, Transferencia
from django.contrib.auth import get_user_model
from rotas.models import Rota, Loja, Parada

User = get_user_model()

class CriarRotaForm(forms.ModelForm):
    motoboy = forms.ModelChoiceField(
        queryset=User.objects.filter(groups__name="Motoboy"),
        required=True,
        label="Motoboy",
        widget=forms.Select(attrs={"class": "form-control"})
    )
    
    # Campo atualizado para usar Select2 (Autocomplete)
    lojas = forms.ModelMultipleChoiceField(
        queryset=Loja.objects.filter(ativa=True).order_by('nome'),
        # Mudamos de Checkbox para SelectMultiple com uma classe para o JS identificar
        widget=forms.SelectMultiple(attrs={
            "class": "form-control select2-multiple",
            "style": "width: 100%"
        }),
        required=False,
        label="Adicionar Paradas (Lojas)"
    )

    class Meta:
        model = Rota
        fields = ['motoboy', 'lojas']

class AdicionarLojaRotaForm(forms.Form):
    loja = forms.ModelChoiceField(queryset=Loja.objects.all(), label="Loja")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Mostrar "Nome - Endereço" no select
        self.fields["loja"].label_from_instance = lambda obj: f"{obj.nome} - {obj.endereco}"
        
class TransferenciaForm(forms.ModelForm):
    TIPO_CHOICES = [
        ('entrada', 'Entrada'),
        ('saida', 'Saída'),
    ]

    tipo = forms.ChoiceField(
        choices=TIPO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    UNIDADES = [
        ("Unidade", "Unidade"),
        ("Caixa", "Caixa"),
        ("Pacote", "Pacote"),
        ("Kg", "Kg"),
        ("Litro", "Litro"),
    ]

    unidade_medida = forms.ChoiceField(
        choices=UNIDADES,
        required=False,
        label="Unidade"
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
            "numero_transferencia",
            "porte_carga",
            "numero_documento",
            "observacoes",
        ]

        widgets = {
            "quantidade": forms.NumberInput(attrs={
                "class": "form-control input-bonitinho-qtd"
            }),
            "data": forms.DateInput(attrs={
                "type": "date",
                "class": "form-control input-bonitinho-data"
            }),
            "numero_transferencia": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "Ex: 65456"
            }),
            "porte_carga": forms.Select(attrs={"class": "input"}),
            "tipo": forms.Select(attrs={"class": "form-control"}),
            "loja_origem": forms.Select(attrs={"class": "form-control"}),
            "loja_destino": forms.Select(attrs={"class": "form-control"}),
            "observacoes": forms.Textarea(attrs={
                "rows": 3,
                "class": "form-control"
            }),
        }

        labels = {
            "tipo": "Tipo",
            "nome_produto": "Nome do Produto",
            "marca": "Marca",
            "quantidade": "Quantidade",
            "fornecedor": "Fornecedor",
            "responsavel": "Responsável",
            "numero_documento": "Nº do Documento (NF/Recibo)",
            "observacoes": "Observações",
            "porte_carga": "Porte da Carga",
        }

    def _get_loja_do_usuario(self, user):
        """
        Busca a loja vinculada ao usuário.

        Primeiro tenta o modelo novo:
        user.perfil.loja

        Depois tenta o modelo antigo:
        user.loja_perfil
        """
        if not user or not user.is_authenticated:
            return None

        perfil = getattr(user, "perfil", None)
        loja_nova = getattr(perfil, "loja", None)

        loja_antiga = getattr(user, "loja_perfil", None)

        return loja_nova or loja_antiga

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        self.user = user

        is_admin = user and (user.is_staff or user.is_superuser)
        user_loja = self._get_loja_do_usuario(user)

        if user and user_loja and not is_admin:
            self.fields["loja_origem"].queryset = Loja.objects.filter(id=user_loja.id)
            self.fields["loja_origem"].initial = user_loja
            self.fields["loja_origem"].empty_label = None

            if "tipo" in self.fields:
                self.fields["tipo"].initial = "saida"
                self.fields["tipo"].disabled = True

    def save(self, commit=True):
        """
        Garante que usuários de loja sempre criem transferência de saída.
        Também evita vincular motorista/retirado_por na criação.
        """
        instance = super().save(commit=False)

        is_admin = self.user and (self.user.is_staff or self.user.is_superuser)
        user_loja = self._get_loja_do_usuario(self.user)

        if self.user and user_loja and not is_admin:
            instance.tipo = "saida"
            instance.loja_origem = user_loja

        instance.motorista = None
        instance.retirado_por = None

        porte_selecionado = self.cleaned_data.get("porte_carga")
        if porte_selecionado:
            instance.tamanho_carga = porte_selecionado

        if commit:
            instance.save()

        return instance