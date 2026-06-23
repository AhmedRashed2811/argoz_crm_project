from django import forms
from .models import Company, Branch, Language


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name', 'slug', 'legal_name', 'timezone', 'currency', 'status', 'logo']


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ['company', 'name', 'address', 'city', 'phone', 'is_active']


class LanguageForm(forms.ModelForm):
    class Meta:
        model = Language
        fields = ['company', 'code', 'name', 'is_default', 'is_active']
