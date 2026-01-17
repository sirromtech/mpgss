# institutions/urls.py
from django.urls import path
from . import views

app_name = 'institutions'

urlpatterns = [
    # Institution management
    path('', views.manage_institutions, name='list'),
    path('manage/', views.manage_institutions, name='manage'),
    path("api/courses/", views.courses_by_institution, name="courses_by_institution"),
    path("get-courses/<int:institution_id>/", views.get_courses, name="get_courses"),
    # -------- FINANCE / APPROVED POOL (MOST SPECIFIC FIRST) --------
    path(
        'pool/<int:institution_id>/finance/',
        views.institution_approved_pool,
        name='approved_pool'
    ),

    # -------- EXPORT --------
    path(
        'pool/<int:institution_id>/<str:pool>/export/',
        views.export_pool_csv,
        name='export_pool_csv'
    ),

    # -------- POOLS --------
    path(
        'pool/<int:institution_id>/<str:pool>/',
        views.institution_pools,
        name='pool_list'
    ),
    path(
        'pool/<int:institution_id>/',
        views.institution_pools,
        name='pool_list_default'
    ),

    # -------- MODALS / AJAX --------
    path(
        'modal/<int:institution_id>/',
        views.institution_modal,
        name='institution_modal'
    ),
    path(
        'modal/add-course/<int:institution_id>/',
        views.add_course_modal,
        name='add_course_modal'
    ),

    # -------- STATS / HELPERS --------
    path(
        'institution_stats/',
        views.institution_stats_view,
        name='institution_stats'
    ),
    path(
        'get-courses/<int:institution_id>/',
        views.get_courses,
        name='get_courses'
    ),
]
