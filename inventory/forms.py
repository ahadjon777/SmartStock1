from django import forms
from django.contrib.auth import get_user_model

from .models import Equipment, Warehouse

User = get_user_model()


class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = ("code", "name", "warehouse")

    def __init__(self, *args, warehouses=None, **kwargs):
        super().__init__(*args, **kwargs)
        if warehouses is not None:
            self.fields["warehouse"].queryset = warehouses


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ("name", "manager")


class StaffForm(forms.Form):
    username = forms.CharField(label="Login", max_length=150)
    full_name = forms.CharField(label="F.I.Sh.", max_length=150, required=False)
    password = forms.CharField(label="Parol (o'zgartirmasangiz bo'sh qoldiring)", widget=forms.PasswordInput, required=False)
    is_admin = forms.BooleanField(label="Admin (hamma narsaga ruxsat)", required=False)
    is_active = forms.BooleanField(label="Faol", required=False, initial=True)
    warehouses = forms.ModelMultipleChoiceField(
        label="Mas'ul bo'lgan omborlar", queryset=Warehouse.objects.all(),
        required=False, widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        clash = User.objects.filter(username__iexact=username)
        if self.user:
            clash = clash.exclude(pk=self.user.pk)
        if clash.exists():
            raise forms.ValidationError("Bunday login band")
        return username

    def clean(self):
        data = super().clean()
        if not self.user and not data.get("password"):
            self.add_error("password", "Yangi xodim uchun parol kerak")
        return data
