# institutions/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.http import Http404
from django.db.models import Count, Sum, F, DecimalField, Q
from .models import Institution, Course
from .forms import CourseForm
from applications.models import Application
from django.core.paginator import Paginator
from django.db.models.functions import Coalesce
from finance.models import Payment
from django.contrib.admin.views.decorators import staff_member_required
import csv
from django.http import HttpResponse, JsonResponse

from decimal import Decimal, ROUND_HALF_UP


def courses_by_institution(request):
    inst_id = request.GET.get("institution_id")
    courses = Course.objects.filter(institution_id=inst_id).values("id", "name", "code")
    return JsonResponse(list(courses), safe=False)

def _format_currency(amount):
    amt = Decimal(amount or 0).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return f"PGK{amt:,.2f}"

def export_pool_csv(request, institution_id, pool='pending'):
    institution = get_object_or_404(Institution, id=institution_id)

    pool_map = {
        'selected': institution.selected_applications(),
        'pending': institution.pending_applications(),
        'rejected': institution.rejected_applications(),
    }
    if pool not in pool_map:
        raise Http404("Unknown pool")

    qs = pool_map[pool].select_related('applicant__user', 'course').order_by('applicant__user__last_name')

    # Prepare response
    filename = f"{institution.name.replace(' ', '_')}_{pool}_pool.csv"
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)

    # Header (customize as needed)
    writer.writerow([institution.name])
    writer.writerow([f"Pool: {pool.capitalize()}"])
    writer.writerow([])

    # Column headers
    writer.writerow(['No.', 'First Name', 'Surname', 'Gender', 'Institution', 'Course', 'Tuition Fee', 'District', 'Year Of Study'])

    subtotal = Decimal('0.00')
    for idx, app in enumerate(qs, start=1):
        tuition = getattr(app.course, 'total_tuition_fee', Decimal('0.00')) or Decimal('0.00')
        subtotal += Decimal(tuition)
        gender = getattr(app.applicant, "gender", "") if app.applicant else ""
        district = getattr(app, "origin_district", "") or getattr(app, "residency_district", "")

        writer.writerow([
            idx,
            app.applicant.user.first_name if app.applicant and app.applicant.user else '',
            app.applicant.user.last_name if app.applicant and app.applicant.user else '',
            gender,
            institution.name,
            app.course.name if app.course else '',
            _format_currency(tuition),
            getattr(app, 'district', '') or '',
            getattr(app, 'year_of_study', '') or '',
        ])

    # Subtotal and grand total (for a single institution grand == subtotal)
    writer.writerow([])
    writer.writerow(['', '', '', '', '', 'Pool total', _format_currency(subtotal)])
    writer.writerow([])

    return response

def manage_institutions(request):
    """
    Show institutions and courses and handle adding a new Course.
    The CourseForm may include the 'institution' field; if not, the template
    posts an 'institution' select and we set the FK explicitly.
    """
    if request.method == 'POST':
        form = CourseForm(request.POST)
        if form.is_valid():
            # If the form includes an institution field, save normally
            if 'institution' in form.cleaned_data and form.cleaned_data.get('institution'):
                form.save()
            else:
                # Otherwise set the FK explicitly from POST data
                inst_id = request.POST.get('institution') or request.POST.get('institution_id')
                if not inst_id:
                    # keep the form and show an error
                    form.add_error(None, "Institution not provided.")
                    institutions = Institution.objects.prefetch_related('courses').all()
                    return render(request, 'institutions/manage_institutions.html', {
                        'form': form,
                        'institutions': institutions
                    })
                institution = get_object_or_404(Institution, pk=inst_id)
                course = form.save(commit=False)
                course.institution = institution
                course.save()
            return redirect('institutions:manage')
        # if invalid, fall through to re-render with errors
    else:
        form = CourseForm()

    institutions = Institution.objects.prefetch_related('courses').all()
    return render(request, 'institutions/manage_institutions.html', {
        'form': form,
        'institutions': institutions
    })

def institution_modal(request, institution_id):
    institution = get_object_or_404(Institution, id=institution_id)
    courses = institution.courses.all()

    # Use Application status constants for safety
    stats = {
        'total': institution.applications_qs().count(),
        'approved': institution.selected_applications().count(),
        'rejected': institution.rejected_applications().count(),
        'pending': institution.pending_applications().count(),
    }
    return render(request, 'institutions/institution_modal.html', {
        'institution': institution,
        'courses': courses,
        'stats': stats
    })


def add_course_modal(request, institution_id):
    institution = get_object_or_404(Institution, id=institution_id)

    if request.method == 'POST':
        form = CourseForm(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.institution = institution
            course.save()
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'errors': form.errors})
    return JsonResponse({'success': False, 'errors': 'Invalid method'}, status=405)


def institution_stats_view(request):
    # Use consistent status keys; 'awarded' was not defined on Application — use STATUS_APPROVED
    institution_stats = (
        Application.objects
        .values('institution__name')
        .annotate(
            applicants=Count('id'),
            awarded=Count('id', filter=Q(status=Application.STATUS_APPROVED))
        )
        .order_by('-applicants')
    )
    return render(request, 'institutions/institution_stats.html', {'institution_stats': institution_stats})


def get_courses(request, institution_id):
    courses = Course.objects.filter(institution_id=institution_id).values('id', 'name')
    return JsonResponse(list(courses), safe=False)


# New: view to show pools for an institution (paginated)

def institution_pools(request, institution_id, pool='pending'):
    institution = get_object_or_404(Institution, id=institution_id)

    pool_map = {
        'selected': institution.selected_applications(),
        'pending': institution.pending_applications(),
        'rejected': institution.rejected_applications(),
    }
    if pool not in pool_map:
        raise Http404("Unknown pool")

    # base queryset for the pool (use select_related to avoid N+1)
    qs = pool_map[pool].select_related('applicant__user', 'course').order_by('-submission_date')

    # total tuition for the entire pool (sum of course.total_tuition_fee)
    pool_total = qs.aggregate(total=Coalesce(Sum('course__total_tuition_fee'), Decimal('0.00')))['total']

    # paginate and compute subtotal for the current page
    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # subtotal for the current page
    page_subtotal = qs.aggregate(total=Coalesce(Sum('course__total_tuition_fee'), Decimal('0.00')))['total']

    return render(request, 'institutions/pool_list.html', {
        'institution': institution,
        'pool_name': pool,
        'page_obj': page_obj,
        'pool_total': pool_total,
        'page_subtotal': page_subtotal,
    })

@staff_member_required
def institution_approved_pool(request, institution_id):
    institution = get_object_or_404(Institution, pk=institution_id)

    base_qs = Application.objects.filter(
        institution=institution,
        status=Application.STATUS_APPROVED
    ).select_related('applicant__user', 'course')

    annotated_qs = base_qs.annotate(
        paid_amount=Coalesce(
            Sum('payments__amount', filter=Q(payments__status=Payment.STATUS_PAID)),
            Decimal('0.00')
        ),
        committed_amount=Coalesce(
            Sum('payments__amount', filter=Q(payments__status=Payment.STATUS_COMMITTED)),
            Decimal('0.00')
        ),
        tuition_fee=F('course__total_tuition_fee'),
    ).annotate(
        outstanding=F('tuition_fee') - F('paid_amount')
    ).order_by('-submission_date')

    paginator = Paginator(annotated_qs, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    totals = annotated_qs.aggregate(
        pool_total_tuition=Coalesce(Sum('tuition_fee'), Decimal('0.00')),
        pool_total_paid=Coalesce(Sum('paid_amount'), Decimal('0.00')),
        pool_total_committed=Coalesce(Sum('committed_amount'), Decimal('0.00')),
    )
    totals['pool_total_outstanding'] = totals['pool_total_tuition'] - totals['pool_total_paid']

    page_subtotal = page_obj.object_list.aggregate(
        page_tuition=Coalesce(Sum('tuition_fee'), Decimal('0.00')),
        page_paid=Coalesce(Sum('paid_amount'), Decimal('0.00')),
        page_committed=Coalesce(Sum('committed_amount'), Decimal('0.00')),
    )
    page_subtotal['page_outstanding'] = page_subtotal['page_tuition'] - page_subtotal['page_paid']

    return render(request, 'institution/approved_pool.html', {
        'institution': institution,
        'page_obj': page_obj,
        'totals': totals,
        'page_subtotal': page_subtotal,
    })

@staff_member_required
def institution_approved_pool_fragment(request, institution_id):
    """
    Return the same template fragment used in approved_pool.html but without
    the full layout — suitable for AJAX/modal insertion.
    """
    institution = get_object_or_404(Institution, pk=institution_id)

    # reuse the same queryset/aggregation logic as above
    base_qs = Application.objects.filter(
        institution=institution,
        status=Application.STATUS_APPROVED
    ).select_related('applicant__user', 'course')

    annotated_qs = base_qs.annotate(
        paid_amount=Coalesce(Sum('payments__amount', filter=Q(payments__status=Payment.STATUS_PAID)), Decimal('0.00')),
        committed_amount=Coalesce(Sum('payments__amount', filter=Q(payments__status=Payment.STATUS_COMMITTED)), Decimal('0.00')),
        tuition_fee=F('course__total_tuition_fee'),
    ).annotate(outstanding=F('tuition_fee') - F('paid_amount')).order_by('-submission_date')

    paginator = Paginator(annotated_qs, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    totals = annotated_qs.aggregate(
        pool_total_tuition=Coalesce(Sum('tuition_fee'), Decimal('0.00')),
        pool_total_paid=Coalesce(Sum('paid_amount'), Decimal('0.00')),
        pool_total_committed=Coalesce(Sum('committed_amount'), Decimal('0.00')),
    )
    totals['pool_total_outstanding'] = totals['pool_total_tuition'] - totals['pool_total_paid']

    return render(request, 'institution/_approved_pool_fragment.html', {
        'institution': institution,
        'page_obj': page_obj,
        'totals': totals,
    })


def get_courses(request, institution_id):
    institution = get_object_or_404(Institution, pk=institution_id)
    courses = Course.objects.filter(institution=institution).order_by("name").values("id", "name")
    return JsonResponse(list(courses), safe=False)
