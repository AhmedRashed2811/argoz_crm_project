from django import forms
from .models import Campaign, CampaignEvent, TVAd, StreetAd, ExhibitionRecord, SocialMediaAd, CampaignOtherCost


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ['company', 'name', 'description', 'start_date', 'end_date', 'target_type', 'target_object_id']
        widgets = {'start_date': forms.DateInput(attrs={'type': 'date'}), 'end_date': forms.DateInput(attrs={'type': 'date'})}


class CampaignEventForm(forms.ModelForm):
    class Meta:
        model = CampaignEvent
        fields = ['campaign', 'event_name', 'venue_place', 'event_date', 'budget', 'target_attendees', 'description', 'logo']
        widgets = {'event_date': forms.DateInput(attrs={'type': 'date'})}


class CampaignApprovalForm(forms.Form):
    new_status = forms.ChoiceField(choices=Campaign.APPROVAL_CHOICES)
    reason = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)
