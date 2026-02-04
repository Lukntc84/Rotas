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
    tipo = forms.ChoiceField(choices=TIPO_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}))
    
    UNIDADES = [
        ("Unidade", "Unidade"),
        ("Caixa", "Caixa"),
        ("Pacote", "Pacote"),
        ("Kg", "Kg"),
        ("Litro", "Litro"),
    ]
    unidade_medida = forms.ChoiceField(choices=UNIDADES, required=False, label="Unidade")

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
            'numero_transferencia': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Ex: 65456'}),
            'porte_carga': forms.Select(attrs={'class': 'input'}),
            "tipo": forms.Select(attrs={"class": "form-control"}),
            "loja_origem": forms.Select(attrs={"class": "form-control"}),
            "loja_destino": forms.Select(attrs={"class": "form-control"}),
            "observacoes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }
        labels = {
            "tipo": "Tipo",
            "nome_produto": "Nome do Produto",
            "marca": "Marca",
            "quantidade": "Quantidade",
            "fornecedor": "Fornecedor",
            "responsavel": "Responsável",
            "motorista": "Motorista",
            "retirado_por": "Retirado por",
            "numero_documento": "Nº do Documento (NF/Recibo)",
            "observacoes": "Observações",
            "porte_carga": "Porte da Carga",
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user and not user.is_staff:
            # Filtra a loja de origem baseada no perfil do usuário logado
            user_loja = getattr(user, 'loja_perfil', None)
            if user_loja:
                self.fields['loja_origem'].queryset = Loja.objects.filter(id=user_loja.id)
                self.fields['loja_origem'].initial = user_loja
                self.fields['loja_origem'].empty_label = None

    def save(self, commit=True):
        """
        Sobrescrevemos o save para garantir que o campo 'tamanho_carga' 
        receba o mesmo valor que o usuário selecionou em 'porte_carga'.
        """
        instance = super().save(commit=False)
        
        # Sincroniza os campos para evitar erro nos filtros da lista
        porte_selecionado = self.cleaned_data.get('porte_carga')
        if porte_selecionado:
            instance.tamanho_carga = porte_selecionado
            
        if commit:
            instance.save()
        return instance