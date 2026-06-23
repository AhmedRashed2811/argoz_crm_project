from django import forms
from .models import Lead, LeadActivity, LeadFollowUp, Meeting


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            'company', 'full_name', 'phone_country_code', 'phone_number', 'email', 'source', 'origin',
            'current_stage', 'language', 'broker', 'campaign', 'how_did_you_know', 'metadata'
        ]
        widgets = {'metadata': forms.Textarea(attrs={'rows': 3})}


class LeadStageChangeForm(forms.ModelForm):
    reason = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)

    class Meta:
        model = Lead
        fields = ['current_stage']


class LeadActivityForm(forms.ModelForm):
    class Meta:
        model = LeadActivity
        fields = ['activity_type', 'subject', 'body', 'result']


class LeadFollowUpForm(forms.ModelForm):
    class Meta:
        model = LeadFollowUp
        fields = ['assigned_to', 'due_at', 'status', 'reminder_at', 'notes']
        widgets = {'due_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}), 'reminder_at': forms.DateTimeInput(attrs={'type': 'datetime-local'})}


class MeetingForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = ['assigned_to', 'scheduled_at', 'location', 'meeting_type', 'status', 'notes']
        widgets = {'scheduled_at': forms.DateTimeInput(attrs={'type': 'datetime-local'})}
