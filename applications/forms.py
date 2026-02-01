
# applications/forms.py (cleaned / fixes)
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.apps import apps
from .models import ApplicantProfile, Application, ApplicationReview
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.contrib.auth import get_user_model
from .validators import validate_upload
from institutions .models import Course, Institution



User = get_user_model()

class ApplicantProfileForm(forms.ModelForm):
    class Meta:
        model = ApplicantProfile
        fields = [
            'photo', 'first_name', 'surname', 'gender', 'date_of_birth',
            'phone_number', 'nid_number', 'grade12_certificate_number',
            'elementary_completed', 'primary_completed',
            'secondary_school_name', 'year_completed_grade12',
            'tesas_category', 'active_student_id',
            'father_name', 'father_occupation', 'father_nationality',
            'father_province', 'father_district', 'father_llg', 'father_village',
            'father_elementary_completed', 'father_primary_completed', 'father_highschool_completed',
            'mother_name', 'mother_occupation', 'mother_nationality',
            'mother_province', 'mother_district', 'mother_llg', 'mother_village',
            'mother_elementary_completed', 'mother_elementary_year',
            'mother_primary_completed', 'mother_primary_year',
            'mother_highschool_completed', 'mother_highschool_year',
            'postal_address', 'current_residential_area',
            'duration_living_in', 'current_district', 'current_llg',
            'origin_province', 'origin_district', 'origin_ward',
            'residency_province', 'residency_district', 'residency_ward',
        ]

        widgets = {
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control-file'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'surname': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'nid_number': forms.TextInput(attrs={'class': 'form-control'}),
            'grade12_certificate_number': forms.TextInput(attrs={'class': 'form-control'}),
            'secondary_school_name': forms.TextInput(attrs={'class': 'form-control'}),
            'year_completed_grade12': forms.NumberInput(attrs={'class': 'form-control'}),
            'tesas_category': forms.Select(attrs={'class': 'form-control'}),
            'active_student_id': forms.TextInput(attrs={'class': 'form-control'}),
            'father_name': forms.TextInput(attrs={'class': 'form-control'}),
            'father_occupation': forms.TextInput(attrs={'class': 'form-control'}),
            'father_nationality': forms.TextInput(attrs={'class': 'form-control'}),
            'father_province': forms.TextInput(attrs={'class': 'form-control'}),
            'father_district': forms.TextInput(attrs={'class': 'form-control'}),
            'father_llg': forms.TextInput(attrs={'class': 'form-control'}),
            'father_village': forms.TextInput(attrs={'class': 'form-control'}),
            'mother_name': forms.TextInput(attrs={'class': 'form-control'}),
            'mother_occupation': forms.TextInput(attrs={'class': 'form-control'}),
            'mother_nationality': forms.TextInput(attrs={'class': 'form-control'}),
            'mother_province': forms.TextInput(attrs={'class': 'form-control'}),
            'mother_district': forms.TextInput(attrs={'class': 'form-control'}),
            'mother_llg': forms.TextInput(attrs={'class': 'form-control'}),
            'mother_village': forms.TextInput(attrs={'class': 'form-control'}),
            'mother_elementary_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'mother_primary_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'mother_highschool_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'parent_company': forms.TextInput(attrs={'class': 'form-control'}),
            'parent_job_title': forms.TextInput(attrs={'class': 'form-control'}),
            'parent_salary_range': forms.TextInput(attrs={'class': 'form-control'}),
            'parent_income_source': forms.TextInput(attrs={'class': 'form-control'}),
            'parent_annual_income': forms.TextInput(attrs={'class': 'form-control'}),
            'student_company': forms.TextInput(attrs={'class': 'form-control'}),
            'student_job_title': forms.TextInput(attrs={'class': 'form-control'}),
            'student_salary_range': forms.TextInput(attrs={'class': 'form-control'}),
            'origin_province': forms.TextInput(attrs={'class': 'form-control'}),
            'origin_district': forms.TextInput(attrs={'class': 'form-control'}),
            'origin_ward': forms.TextInput(attrs={'class': 'form-control'}),
            'residency_province': forms.TextInput(attrs={'class': 'form-control'}),
            'residency_district': forms.TextInput(attrs={'class': 'form-control'}),
            'residency_ward': forms.TextInput(attrs={'class': 'form-control'}),
            'current_residential_area': forms.TextInput(attrs={'class': 'form-control'}),
            'duration_living_in': forms.TextInput(attrs={'class': 'form-control'}),
            'current_district': forms.TextInput(attrs={'class': 'form-control'}),
            'current_llg': forms.TextInput(attrs={'class': 'form-control'}),
        }


class ApplicationForm(forms.ModelForm):
    institution = forms.ModelChoiceField(queryset=None, required=True)
    course = forms.ModelChoiceField(queryset=None, required=False)


    class Meta:
        model = Application
        fields = [
            # Study details
            "institution",
            "course",
            "year_of_study",

            # ✅ Single PDF upload
            "documents_pdf",

            # Parent employment (MANDATORY LOGIC BELOW)
            "parent_employed",
            "parent_company",
            "parent_job_title",
            "parent_salary_range",
            "parent_income_source",
            "parent_annual_income",

            # Student employment
            "student_employed",
            "student_company",
            "student_job_title",
            "student_salary_range",

            # Origin
            "origin_province",
            "origin_district",
            "origin_ward",

            # Residency
            "residency_province",
            "residency_district",
            "residency_ward",
        ]

        widgets = {
            "documents_pdf": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": ".pdf",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        Institution = apps.get_model("institutions", "Institution")
        Course = apps.get_model("institutions", "Course")

        self.fields["institution"].queryset = Institution.objects.all()
        self.fields["course"].queryset = Course.objects.none()

        # Preload courses if editing
        if self.instance.pk and self.instance.institution_id:
            self.fields["course"].queryset = Course.objects.filter(
                institution_id=self.instance.institution_id
            )

        # Load courses from POST
        inst_id = self.data.get("institution") or self.initial.get("institution")
        if inst_id:
            self.fields["course"].queryset = Course.objects.filter(
                institution_id=inst_id
            )

    # -------------------------
    # VALIDATION
    # -------------------------

    def clean_documents_pdf(self):
        f = self.cleaned_data.get("documents_pdf")
        if not f:
            raise forms.ValidationError("You must upload a PDF containing all required documents.")

        if not f.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Only PDF files are allowed.")

        if f.size > 10 * 1024 * 1024:
            raise forms.ValidationError("File size must be under 10MB.")

        return f

    def clean(self):
        cleaned = super().clean()

        # Parent employment logic
        if cleaned.get("parent_employed"):
            required = [
                "parent_company",
                "parent_job_title",
                "parent_salary_range",
                "parent_income_source",
                "parent_annual_income",
            ]
            for field in required:
                if not cleaned.get(field):
                    self.add_error(field, "This field is required when parent is employed.")

        # Student employment logic
        if cleaned.get("student_employed"):
            required = [
                "student_company",
                "student_job_title",
                "student_salary_range",
            ]
            for field in required:
                if not cleaned.get(field):
                    self.add_error(field, "This field is required when student is employed.")

        return cleaned

class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text="Required. Enter a valid email address.")
    first_name = forms.CharField(max_length=30, required=True, help_text="Your given name.")
    last_name = forms.CharField(max_length=30, required=True, help_text="Your surname.")

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with that email already exists.")
        return email


class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with that email already exists.")
        return email


class UserLoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'autofocus': True}))
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'})
    )


class ContinuingApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = [
            "year_of_study",
            "documents_pdf",
        ]
        widgets = {
            "documents_pdf": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": ".pdf",
                }
            ),
        }

    def clean_documents_pdf(self):
        f = self.cleaned_data.get("documents_pdf")
        if not f:
            raise forms.ValidationError("You must upload a PDF containing all required documents.")
        if not f.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Only PDF files are allowed.")
        if f.size > 10 * 1024 * 1024:
            raise forms.ValidationError("File size must be under 10MB.")
        return f

class ContinuingProfileForm(forms.ModelForm):
    class Meta:
        model = ApplicantProfile
        fields = [
            "photo",
            "first_name",
            "surname",
            "gender",
            "phone_number",
            "postal_address",
            "current_residential_area",
            "current_district",
            "current_llg",
            "origin_province",
            "origin_district",
            "origin_ward",
            "active_student_id",

        ]
        widgets = {
            "photo": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "surname": forms.TextInput(attrs={"class": "form-control"}),
            "gender": forms.Select(attrs={"class": "form-control"}),
            "phone_number": forms.TextInput(attrs={"class": "form-control"}),
            "postal_address": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "current_residential_area": forms.TextInput(attrs={"class": "form-control"}),
            "current_district": forms.TextInput(attrs={"class": "form-control"}),
            "current_llg": forms.TextInput(attrs={"class": "form-control"}),
            "origin_district": forms.TextInput(attrs={"class": "form-control"}),  # keep only once
            "origin_ward": forms.TextInput(attrs={"class": "form-control"}),
            "active_student_id": forms.TextInput(attrs={"class": "form-control"}),

        }

    def clean_photo(self):
        photo = self.cleaned_data.get("Photo")
        if photo:
            return validate_upload(photo, "Profile photo")
        return photo

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("first_name", "surname"):
            if field_name in self.fields:
                self.fields[field_name].disabled = True
                self.fields[field_name].required = False
                self.fields[field_name].widget.attrs["readonly"] = True



class ApplicationReviewForm(forms.ModelForm):
    class Meta:
        model = ApplicationReview
        fields = ["status", "note"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-control"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }


class LegacyLookupForm(forms.Form):
    first_name = forms.CharField(max_length=100, required=True)
    surname = forms.CharField(max_length=100, required=True)
    year_of_study = forms.IntegerField(required=False)

class ContinuingTranscriptOnlyForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ["documents_pdf"]
        widgets = {
            "documents_pdf": forms.ClearableFileInput(
                attrs={"class": "form-control", "accept": ".pdf"}
            )
        }
