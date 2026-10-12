from django.contrib.auth import views as auth_views
from django.urls import path

from core.throttling import rate_limit

from . import views
from .forms import (
    StyledAuthenticationForm,
    StyledPasswordChangeForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)


app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("register/professional/", views.professional_register, name="professional_register"),
    path(
        "login/",
        rate_limit("login", 10, 15 * 60, methods={"POST"}, body_fields={"username"})(
            views.MediMartLoginView.as_view(authentication_form=StyledAuthenticationForm)
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "password-change/",
        auth_views.PasswordChangeView.as_view(form_class=StyledPasswordChangeForm),
        name="password_change",
    ),
    path(
        "password-change/done/",
        auth_views.PasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path(
        "password-reset/",
        rate_limit("password-reset", 5, 60 * 60, methods={"POST"}, body_fields={"email"})(
            auth_views.PasswordResetView.as_view(form_class=StyledPasswordResetForm)
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(form_class=StyledSetPasswordForm),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile, name="profile"),
    path("login/verify/", views.mfa_challenge, name="mfa_challenge"),
    path("profile/security/two-factor/", views.mfa_settings, name="mfa_settings"),
    path("addresses/", views.address_list, name="address_list"),
    path("addresses/add/", views.address_create, name="address_create"),
    path("addresses/<int:pk>/edit/", views.address_update, name="address_update"),
    path("addresses/<int:pk>/delete/", views.address_delete, name="address_delete"),
]
