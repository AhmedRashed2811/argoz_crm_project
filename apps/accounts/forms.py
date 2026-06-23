from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import Group, Permission
from .models import User, UserProfile, SalesProfile, BrokerProfile, Team, TeamMembership


def decorate_fields(form):
    for name, field in form.fields.items():
        widget = field.widget
        existing = widget.attrs.get('class', '')
        if not isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect)):
            widget.attrs['class'] = (existing + ' form-control').strip()
    return form


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email')


class CRMUserCreationForm(UserCreationForm):
    primary_group = forms.ModelChoiceField(queryset=Group.objects.all().order_by('name'), required=False, help_text='Primary default role template. Its permissions are copied to the user, but can be changed below.')
    groups = forms.ModelMultipleChoiceField(queryset=Group.objects.all().order_by('name'), required=False, widget=forms.CheckboxSelectMultiple)
    user_permissions = forms.ModelMultipleChoiceField(queryset=Permission.objects.select_related('content_type').all().order_by('content_type__app_label','codename'), required=False, widget=forms.CheckboxSelectMultiple)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ['company', 'email', 'username', 'first_name', 'last_name', 'phone', 'is_active', 'is_staff', 'primary_group', 'groups', 'user_permissions']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        decorate_fields(self)
        if user and not user.is_superuser:
            self.fields['company'].initial = user.company
            self.fields['company'].disabled = True


    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            selected_groups = list(self.cleaned_data.get('groups') or [])
            primary = self.cleaned_data.get('primary_group')
            if primary and primary not in selected_groups:
                selected_groups.insert(0, primary)
            if selected_groups:
                user.groups.set(selected_groups)
                # Copy template permissions as defaults; direct permissions can still be edited later.
                perms = Permission.objects.filter(group__in=selected_groups).distinct()
                user.user_permissions.add(*perms)
            explicit_perms = self.cleaned_data.get('user_permissions')
            if explicit_perms is not None:
                user.user_permissions.set(explicit_perms)
        return user


class CRMUserUpdateForm(forms.ModelForm):
    primary_group = forms.ModelChoiceField(queryset=Group.objects.all().order_by('name'), required=False, help_text='Used only as a visual default template; effective permissions are saved per user.')
    groups = forms.ModelMultipleChoiceField(queryset=Group.objects.all().order_by('name'), required=False, widget=forms.CheckboxSelectMultiple)
    user_permissions = forms.ModelMultipleChoiceField(queryset=Permission.objects.select_related('content_type').all().order_by('content_type__app_label','codename'), required=False, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = User
        fields = ['company', 'email', 'username', 'first_name', 'last_name', 'phone', 'is_active', 'is_staff', 'primary_group', 'groups', 'user_permissions']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        decorate_fields(self)
        if user and not user.is_superuser:
            self.fields['company'].initial = user.company
            self.fields['company'].disabled = True
        if self.instance and self.instance.pk:
            self.fields['groups'].initial = self.instance.groups.all()
            self.fields['user_permissions'].initial = self.instance.user_permissions.all()
            self.fields['primary_group'].initial = self.instance.groups.first()

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            groups = list(self.cleaned_data.get('groups') or [])
            primary = self.cleaned_data.get('primary_group')
            if primary and primary not in groups:
                groups.insert(0, primary)
            user.groups.set(groups)
            user.user_permissions.set(self.cleaned_data.get('user_permissions') or [])
        return user


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['display_name', 'job_title', 'avatar', 'default_group_template', 'metadata']


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['company', 'name', 'code', 'sales_head', 'is_active', 'sort_order']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        decorate_fields(self)
        if user and not user.is_superuser:
            self.fields['company'].initial = user.company
            self.fields['company'].disabled = True
            self.fields['sales_head'].queryset = User.objects.filter(company=user.company, is_active=True)
