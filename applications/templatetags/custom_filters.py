# applications/templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter
def dict_lookup(value, key):
    """
    Safely look up a key in a dict.
    Usage: {{ my_dict|dict_lookup:key }}
    """
    if isinstance(value, dict):
        return value.get(key)
    return None
