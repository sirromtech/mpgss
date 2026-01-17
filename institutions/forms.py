# institutions/forms.py
from django import forms
from .models import Course, Institution


class CourseForm(forms.ModelForm):
    institution = forms.ModelChoiceField(
        queryset=Institution.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Course
        fields = ['institution', 'name', 'code', 'years_of_study', 'total_tuition_fee']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. CS, EE, ACC'}),
            'years_of_study': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'total_tuition_fee': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def clean_code(self):
        code = self.cleaned_data.get("code", "").strip().upper()
        if not code:
            raise forms.ValidationError("Course code is required.")
        return code

    def clean_total_tuition_fee(self):
        fee = self.cleaned_data.get("total_tuition_fee")
        if fee is None:
            raise forms.ValidationError("Tuition fee is required.")
        if fee < 0:
            raise forms.ValidationError("Tuition fee cannot be negative.")
        return fee

    def clean(self):
        cleaned = super().clean()
        institution = cleaned.get("institution")
        code = cleaned.get("code")

        if institution and code:
            qs = Course.objects.filter(institution=institution, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    f"A course with code '{code}' already exists for this institution."
                )
        return cleaned
