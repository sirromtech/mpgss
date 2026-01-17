# finance/permissions.py
from django.contrib.auth.decorators import user_passes_test

SECTION32_GROUP = "Section32 Officers"
FINANCE_GROUP = "Finance Officers"

def is_section32_or_finance(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=[SECTION32_GROUP, FINANCE_GROUP]).exists()


section32_required = user_passes_test(is_section32_or_finance)
