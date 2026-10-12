from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.models import UserProfile
from accounts.permissions import role_allowed

from .forms import ContentIssueForm, DoctorProfileForm, SupportMessageForm, SupportTicketForm
from .models import BlogCategory, BlogPost, ContentIssue, DoctorProfile, Notification, SupportTicket
from .services import create_notification


SUPPORT_ROLES = {
    UserProfile.Role.ADMIN,
    UserProfile.Role.OPERATIONS_MANAGER,
    UserProfile.Role.SUPPORT_STAFF,
}


def user_can_manage_support(user):
    return role_allowed(user, SUPPORT_ROLES, allow_staff=True)


@login_required
def notification_list(request):
    notifications = request.user.notifications.all()
    return render(
        request,
        "extras/notification_list.html",
        {"notifications": notifications},
    )


@login_required
@require_POST
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    return redirect(notification.link or "extras:notification_list")


@login_required
def support_ticket_list(request):
    can_manage_support = user_can_manage_support(request.user)
    if can_manage_support:
        tickets = SupportTicket.objects.select_related("user").all()
    else:
        tickets = request.user.support_tickets.all()
    return render(
        request,
        "extras/support_ticket_list.html",
        {"tickets": tickets, "can_manage_support": can_manage_support},
    )


@login_required
def support_ticket_create(request):
    if request.method == "POST":
        form = SupportTicketForm(request.POST, request.FILES)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.user = request.user
            ticket.save()
            create_notification(
                request.user,
                "Support ticket created",
                f"Your ticket #{ticket.pk} was created. MediMart support will review it.",
                Notification.NotificationType.SUPPORT,
                ticket.get_absolute_url() if hasattr(ticket, "get_absolute_url") else "",
            )
            messages.success(request, "Support ticket created.")
            return redirect("extras:support_ticket_detail", pk=ticket.pk)
    else:
        form = SupportTicketForm()

    return render(
        request,
        "extras/support_ticket_form.html",
        {"form": form},
    )


@login_required
def support_ticket_detail(request, pk):
    can_manage_support = user_can_manage_support(request.user)
    if can_manage_support:
        ticket = get_object_or_404(SupportTicket, pk=pk)
    else:
        ticket = get_object_or_404(SupportTicket, pk=pk, user=request.user)

    if request.method == "POST":
        form = SupportMessageForm(request.POST, request.FILES)
        if form.is_valid():
            reply = form.save(commit=False)
            reply.ticket = ticket
            reply.sender = request.user
            reply.is_staff_reply = can_manage_support
            reply.save()
            if can_manage_support and ticket.status == SupportTicket.Status.OPEN:
                ticket.status = SupportTicket.Status.IN_PROGRESS
                ticket.save(update_fields=["status", "updated_at"])
            if can_manage_support and ticket.user != request.user:
                create_notification(
                    ticket.user,
                    "Support replied",
                    f"MediMart support replied to ticket #{ticket.pk}.",
                    Notification.NotificationType.SUPPORT,
                    "",
                )
            messages.success(request, "Reply added.")
            return redirect("extras:support_ticket_detail", pk=ticket.pk)
    else:
        form = SupportMessageForm()

    return render(
        request,
        "extras/support_ticket_detail.html",
        {
            "ticket": ticket,
            "reply_form": form,
            "can_manage_support": can_manage_support,
        },
    )


def blog_list(request):
    posts = BlogPost.objects.filter(status=BlogPost.Status.PUBLISHED).select_related(
        "category",
        "author",
    )
    query = request.GET.get("q", "").strip()
    if query:
        posts = posts.filter(
            Q(title__icontains=query)
            | Q(excerpt__icontains=query)
            | Q(content__icontains=query)
            | Q(category__name__icontains=query)
        )
    featured_post = posts.first() if not query and not request.GET.get("page") else None
    if featured_post:
        posts = posts.exclude(pk=featured_post.pk)
    paginator = Paginator(posts, 9)
    page_obj = paginator.get_page(request.GET.get("page"))
    categories = BlogCategory.objects.annotate(
        published_count=Count(
            "posts",
            filter=Q(posts__status=BlogPost.Status.PUBLISHED),
        )
    ).filter(published_count__gt=0)
    return render(
        request,
        "extras/blog_list.html",
        {
            "page_obj": page_obj,
            "posts": page_obj.object_list,
            "page_title": "Health Blog",
            "page_description": "Practical, clinician-aware guides for everyday health and safer product use.",
            "featured_post": featured_post,
            "categories": categories,
            "query": query,
        },
    )


def blog_category(request, slug):
    category = get_object_or_404(BlogCategory, slug=slug)
    posts = category.posts.filter(status=BlogPost.Status.PUBLISHED).select_related("author")
    query = request.GET.get("q", "").strip()
    if query:
        posts = posts.filter(
            Q(title__icontains=query) | Q(excerpt__icontains=query) | Q(content__icontains=query)
        )
    paginator = Paginator(posts, 9)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "extras/blog_list.html",
        {
            "category": category,
            "page_obj": page_obj,
            "posts": page_obj.object_list,
            "page_title": category.name,
            "page_description": category.description or "Health education articles.",
            "categories": BlogCategory.objects.annotate(
                published_count=Count(
                    "posts",
                    filter=Q(posts__status=BlogPost.Status.PUBLISHED),
                )
            ).filter(published_count__gt=0),
            "query": query,
        },
    )


def blog_detail(request, slug):
    post = get_object_or_404(
        BlogPost.objects.select_related("category", "author"),
        slug=slug,
        status=BlogPost.Status.PUBLISHED,
    )
    related_posts = BlogPost.objects.filter(status=BlogPost.Status.PUBLISHED).exclude(pk=post.pk)
    if post.category_id:
        related_posts = related_posts.filter(category=post.category)
    return render(
        request,
        "extras/blog_detail.html",
        {"post": post, "related_posts": related_posts.select_related("category")[:3], "content_issue_form": ContentIssueForm()},
    )


@require_POST
def content_issue_create(request, kind, identifier):
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = ""
    form = ContentIssueForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please describe the issue before submitting it.")
        return redirect(next_url or "extras:blog_list")
    issue = form.save(commit=False)
    issue.reporter = request.user if request.user.is_authenticated else None
    if kind == "blog":
        issue.blog_post = get_object_or_404(BlogPost, pk=identifier, status=BlogPost.Status.PUBLISHED)
    elif kind == "product":
        from products.models import Product
        issue.product = get_object_or_404(Product, pk=identifier, is_active=True)
    else:
        messages.error(request, "This content cannot be reported.")
        return redirect(next_url or "extras:blog_list")
    issue.save()
    messages.success(request, "Thanks. Our content team will review this report.")
    return redirect(next_url or (issue.blog_post.get_absolute_url() if issue.blog_post else "products:product_list"))


def doctor_list(request):
    doctors = DoctorProfile.objects.filter(is_verified=True).select_related("user")
    return render(request, "extras/doctor_list.html", {"doctors": doctors})


def doctor_detail(request, pk):
    doctor = get_object_or_404(
        DoctorProfile.objects.select_related("user"),
        pk=pk,
        is_verified=True,
    )
    return render(request, "extras/doctor_detail.html", {"doctor": doctor})


def user_can_access_doctor_dashboard(user):
    if not user.is_authenticated:
        return False
    profile = getattr(user, "profile", None)
    return bool(profile and profile.role == UserProfile.Role.DOCTOR)


@login_required
def doctor_dashboard(request):
    if not user_can_access_doctor_dashboard(request.user):
        messages.error(request, "Doctor dashboard access is limited to doctor accounts.")
        return redirect("accounts:dashboard")

    default_name = request.user.get_full_name() or request.user.username
    doctor_profile, created = DoctorProfile.objects.get_or_create(
        user=request.user,
        defaults={
            "full_name": default_name,
            "specialization": "General Medicine",
        },
    )

    if request.method == "POST":
        form = DoctorProfileForm(request.POST, request.FILES, instance=doctor_profile)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.is_verified = False
            profile.verified_by = None
            profile.verified_at = None
            profile.save()
            messages.success(request, "Doctor profile updated and submitted for verification.")
            return redirect("extras:doctor_dashboard")
    else:
        form = DoctorProfileForm(instance=doctor_profile)

    return render(
        request,
        "extras/doctor_dashboard.html",
        {
            "doctor_profile": doctor_profile,
            "form": form,
        },
    )
